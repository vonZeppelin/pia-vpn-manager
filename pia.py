#!/usr/bin/env python3

import cgi, json, subprocess, sys
import http.server as server
import urllib.request as request

from collections import ChainMap
from html import escape
from os import path
from string import Template

ME_DIR = path.dirname(path.abspath(__file__))
TMISSION_DAEMON_NAME = "transmission-daemon"
VPN_DAEMON_NAME = "pia-vpn"
TMISSION_CFG = "/etc/transmission-daemon/settings.json"
PIA_CLIENT_ID = "<put_random_id_here>"


def start_vpn():
    subprocess.run(
        [
            "openvpn",
            "--config", "Netherlands.ovpn",
            "--auth-user-pass", "pia-passwd",
            "--dev", "pia-tun",
            "--dev-type", "tun",
            "--daemon", VPN_DAEMON_NAME,
            "--script-security", "2",
            "--up", path.join(ME_DIR, "trampoline.sh \"up\""),
            "--down", path.join(ME_DIR, "trampoline.sh \"down\""),
            "--up-restart",
            "--persist-tun"
        ],
        cwd=path.join(ME_DIR, "pia"),
        check=True
    )


def stop_vpn():
    subprocess.run(["pkill", "-SIGTERM", "-f", VPN_DAEMON_NAME])


def request_pia_fw_port():
    api_url = "http://209.222.18.222:2000/?client_id=" + PIA_CLIENT_ID
    with request.urlopen(api_url) as resp:
        resp_charset = resp.info().get_param('charset') or 'ascii'
        resp_str = resp.read().decode(resp_charset)
        return int(json.loads(resp_str)["port"])


def exec_tmission_cmd(cmd):
    subprocess.run(["/etc/init.d/" + TMISSION_DAEMON_NAME, cmd])


def update_tmission_settings(bind_addr, bind_port):
    with open(TMISSION_CFG + ".tpl") as settings_tpl:
        settings = Template(settings_tpl.read()).safe_substitute(
            bindaddr=bind_addr, bindport=bind_port
        )
    with open(TMISSION_CFG, "w") as settings_file:
        settings_file.write(settings)


def process_openvpn_cmd(cmd, bind_addr, evt):
    if cmd == "up":
        if evt == "init":
            fw_port = request_pia_fw_port()
            update_tmission_settings(bind_addr, fw_port)
        exec_tmission_cmd("start")
    elif cmd == "down":
        exec_tmission_cmd("stop")
    else:
        print("Unknown command")


def start_web_server():
    class RequestHandler(server.BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()

            with open(path.join(ME_DIR, "pia.html")) as html_file:
                tpl_params = ChainMap(
                    self._get_process_status(TMISSION_DAEMON_NAME, "tmission"),
                    self._get_process_status(VPN_DAEMON_NAME, "pia")
                )
                html = Template(html_file.read()).safe_substitute(**tpl_params)
                self.wfile.write(bytes(html, "utf-8"))

        def do_POST(self):
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={"REQUEST_METHOD": self.command}
            )
            service = form.getvalue("service")
            cmd = form.getvalue("cmd")

            if service == "tmission":
                exec_tmission_cmd(cmd)
            elif service == "pia":
                if cmd == "start":
                    start_vpn()
                elif cmd == "stop":
                    stop_vpn()

            self.send_response(301)
            self.send_header("Location", "/")
            self.end_headers()

        @staticmethod
        def _get_process_status(process_name, key_prefix):
            if subprocess.run(["pgrep", "-f", process_name]).returncode == 0:
                icon, status = "thumbs-up", "running"
            else:
                icon, status = "thumbs-down", "not running"
            return {
                key_prefix + "icon": icon,
                key_prefix + "status": status
            }

    httpd = server.HTTPServer(('', 8888), RequestHandler)
    httpd.serve_forever()


def main():
    argc = len(sys.argv)
    if argc == 1:
        start_web_server()
        return
    elif argc == 2:
        cmd = sys.argv[1]
        if cmd == "start":
            start_vpn()
        elif cmd == "stop":
            stop_vpn()
        return
    elif argc == 8:
        cmd, _, _, _, bind_addr, _, evt = sys.argv[1:]
        process_openvpn_cmd(cmd, bind_addr, evt)
        return

    print("Illegal arguments specified")
    sys.exit(1)


if __name__ == "__main__":
    main()
