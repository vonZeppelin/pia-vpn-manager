#!/usr/bin/env python3

import cgi, collections, json, subprocess, sys
import http.server as server
import urllib.request as request

from http import HTTPStatus
from os import path
from string import Template

ME = path.abspath(__file__)
ME_DIR = path.dirname(ME)
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
            "--up", ME + " \"up\"",
            "--down", ME + " \"down\"",
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
    with request.urlopen(api_url, timeout=5) as resp:
        resp_charset = resp.info().get_param('charset') or 'ascii'
        resp_str = resp.read().decode(resp_charset)
        return int(json.loads(resp_str)["port"])


def exec_tmission_cmd(cmd):
    subprocess.run(
        ["/etc/init.d/" + TMISSION_DAEMON_NAME, cmd],
        stdout=subprocess.DEVNULL
    )


def exec_pia_cmd(cmd):
    if cmd == "start":
        start_vpn()
    elif cmd == "stop":
        stop_vpn()


def update_tmission_settings(bind_addr, bind_port):
    with open(TMISSION_CFG + ".tpl") as settings_tpl:
        settings = json.load(settings_tpl)
        settings.update({
            "bind-address-ipv4": bind_addr,
            "peer-port": bind_port
        })
    with open(TMISSION_CFG, "w") as settings_file:
        json.dump(settings, settings_file)


def process_openvpn_evt(cmd, bind_addr, evt):
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
    with open(path.join(ME_DIR, "pia.html")) as html_file:
        html_template = Template(html_file.read())

    class RequestHandler(server.BaseHTTPRequestHandler):
        def log_message(*args):
            pass

        def do_HEAD(self):
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-type", "text/html")
            self.end_headers()

        def do_GET(self):
            tpl_params = collections.ChainMap(
                self._get_process_status(TMISSION_DAEMON_NAME, "tmission"),
                self._get_process_status(VPN_DAEMON_NAME, "pia")
            )
            html = html_template.safe_substitute(**tpl_params)
            self.do_HEAD()
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
                exec_pia_cmd(cmd)

            self.send_response(HTTPStatus.MOVED_PERMANENTLY)
            self.send_header("Location", "/")
            self.end_headers()

        @staticmethod
        def _get_process_status(process_name, key_prefix):
            proc = subprocess.run(
                ["pgrep", "-f", process_name],
                stdout=subprocess.DEVNULL
            )
            if proc.returncode:
                icon, status = "thumbs-down", "not running"
            else:
                icon, status = "thumbs-up", "running"
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
    elif argc == 2:
        exec_pia_cmd(sys.argv[1])
    elif argc == 4:
        process_openvpn_evt(*sys.argv[1:])
    elif argc == 8:
        # OpenVPN doesn't allow packets to go through a tunnel until the script
        # returns with 0 exit code - self-spawn the sript to request a fw port
        cmd, _, _, _, bind_addr, _, evt = sys.argv[1:]
        subprocess.Popen([ME, cmd, bind_addr, evt])
    else:
        print("Illegal arguments specified")
        sys.exit(1)


if __name__ == "__main__":
    main()
