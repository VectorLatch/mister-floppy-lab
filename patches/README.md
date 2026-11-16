# Isolated experimental patches

The starting baseline contains **no patches**. Future changes go in `fpga/*.patch` and/or `main/*.patch`, generated using `git diff`, one fix per pull request. CI applies them in filename order to the exact upstream source SHA. Never commit proprietary disk images, ROMs or personal diagnostic logs.
