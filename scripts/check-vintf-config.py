"""Check the kernel-config portion of one device's VINTF matrix, offline.

This does not replace libvintf's complete HAL/AVB/runtime compatibility check.
"""
import argparse
import json
import pathlib
import re
import xml.etree.ElementTree as ET


def check(config_path, matrix_path, version, level):
    config = {}
    for line in pathlib.Path(config_path).read_text().splitlines():
        if line.startswith('CONFIG_') and '=' in line:
            key, value = line.split('=', 1)
            config[key] = value
    failures, checked, applicable = [], 0, 0
    current = tuple(int(v) for v in version.split('.'))

    def matches(node):
        key, value = node.findtext('key'), node.find('value')
        expected = value.text or ''
        actual = config.get(key, 'n')
        kind = value.attrib['type']
        if kind == 'string':
            actual = actual.strip('"')
        elif kind == 'int':
            try:
                return int(actual, 0) == int(expected, 0)
            except ValueError:
                return False
        elif kind != 'tristate':
            raise ValueError('Unsupported VINTF config type: ' + kind)
        return actual == expected

    for kernel in ET.parse(matrix_path).getroot().findall('kernel'):
        minimum = tuple(int(v) for v in kernel.attrib['version'].split('.'))
        if minimum[:2] != current[:2] or current < minimum or int(kernel.attrib.get('level', level)) != level:
            continue
        conditions = kernel.find('conditions')
        if conditions is not None and not all(matches(c) for c in conditions.findall('config')):
            continue
        applicable += 1
        for node in kernel.findall('config'):
            checked += 1
            if not matches(node):
                key = node.findtext('key')
                failures.append({'key': key, 'expected': node.findtext('value'), 'actual': config.get(key, 'n'),
                                 'kernel_requirement': kernel.attrib})
    if applicable == 0:
        raise ValueError('No applicable kernel requirements found')
    return {'matrix': str(matrix_path), 'config': str(config_path), 'kernel': version, 'level': level,
            'applicable_sections': applicable, 'checked_requirements': checked, 'failures': failures}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('config')
    p.add_argument('matrix')
    p.add_argument('--kernel', default='4.14.336')
    p.add_argument('--level', type=int, default=3)
    p.add_argument('--report')
    a = p.parse_args()
    report = check(a.config, a.matrix, a.kernel, a.level)
    content = json.dumps(report, indent=2) + '\n'
    if a.report:
        pathlib.Path(a.report).write_text(content)
    print(content)
    raise SystemExit(bool(report['failures']))
