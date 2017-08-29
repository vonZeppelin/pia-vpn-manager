pia-vpn-manager
==============

The `pia.py` script manages connections to PIA VPN servers and starts / stops
Transmission daemon when a VPN connection is up or down respectively.

When executed without arguments, the script starts a web server on port `8888`
providing a simple UI with statuses of the Transmission and PIA VPN daemons and
also giving controls to start / stop these daemons.
