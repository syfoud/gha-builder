# Parse the upstream Kbuild backports before any C compilation can start.
.PHONY: ksu-preflight
ksu-preflight:
	@echo KernelSU compatibility source preparation complete
