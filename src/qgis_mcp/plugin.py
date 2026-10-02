"""QGIS plugin: a local socket that runs the MCP server's commands in QGIS.

Protocol (one JSON line each way):
  request:  {"command": "<name>", "params": {...}}
  response: {"status": "ok", "result": ...} or {"status": "error", "message": "..."}

Commands run on QGIS's main thread, inside the open project.
"""

import json
import os

from qgis.core import Qgis, QgsMessageLog, QgsProject
from qgis.PyQt.QtNetwork import QHostAddress, QTcpServer

from .commands import MapCommands

HOST = "127.0.0.1"
PORT = int(os.environ.get("QGIS_MCP_PORT", "9876"))
LOG_TAG = "QGIS MCP"


class QgisMcpPlugin:
    def __init__(self, iface, port=PORT):
        self.iface = iface
        self.port = port
        self.server = None
        self.action = None
        self.commands = MapCommands(QgsProject.instance(), iface)
        self._buffers = {}

    def initGui(self):
        from qgis.PyQt.QtWidgets import QAction

        self.action = QAction("QGIS MCP: iniciar servidor", self.iface.mainWindow())
        self.action.setCheckable(True)
        self.action.toggled.connect(self._toggle)
        self.iface.addPluginToMenu("QGIS MCP", self.action)
        self.iface.addToolBarIcon(self.action)
        if os.environ.get("QGIS_MCP_AUTOSTART", "1") != "0":
            self.action.setChecked(True)

    def unload(self):
        self.stop()
        if self.action:
            self.iface.removePluginMenu("QGIS MCP", self.action)
            self.iface.removeToolBarIcon(self.action)

    def _toggle(self, checked):
        if checked:
            self.start()
        else:
            self.stop()

    def start(self):
        if self.server:
            return True
        self.server = QTcpServer()
        if not self.server.listen(QHostAddress(HOST), self.port):
            self._log(f"No se pudo escuchar en {HOST}:{self.port}: {self.server.errorString()}", Qgis.Critical)
            self.server = None
            if self.action:
                self.action.setChecked(False)
            return False
        self.server.newConnection.connect(self._on_new_connection)
        if self.action:
            self.action.setText("QGIS MCP: detener servidor")
        self._log(f"Escuchando en {HOST}:{self.port}")
        return True

    def stop(self):
        if self.server:
            self.server.close()
            self.server = None
            self._log("Servidor detenido")
        if self.action:
            self.action.setText("QGIS MCP: iniciar servidor")

    def _on_new_connection(self):
        while self.server and self.server.hasPendingConnections():
            sock = self.server.nextPendingConnection()
            self._buffers[sock] = b""
            sock.readyRead.connect(lambda s=sock: self._on_ready_read(s))
            sock.disconnected.connect(lambda s=sock: self._on_disconnected(s))

    def _on_disconnected(self, sock):
        self._buffers.pop(sock, None)
        sock.deleteLater()

    def _on_ready_read(self, sock):
        self._buffers[sock] = self._buffers.get(sock, b"") + bytes(sock.readAll())
        if b"\n" not in self._buffers[sock]:
            return
        line, _, rest = self._buffers[sock].partition(b"\n")
        self._buffers[sock] = rest
        response = self.dispatch(line)
        sock.write((json.dumps(response, ensure_ascii=False, default=str) + "\n").encode("utf-8"))
        sock.flush()
        sock.disconnectFromHost()

    def dispatch(self, line):
        try:
            request = json.loads(line.decode("utf-8") if isinstance(line, bytes) else line)
            command = request.get("command")
            handler = self.commands.handlers().get(command)
            if handler is None:
                return {"status": "error", "message": f"Orden desconocida: {command}"}
            result = handler(**(request.get("params") or {}))
            return {"status": "ok", "result": result}
        except Exception as exc:  # cualquier fallo vuelve al cliente como error
            message = exc.args[0] if isinstance(exc, KeyError) and exc.args else str(exc)
            self._log(f"Error ejecutando orden: {message}", Qgis.Warning)
            return {"status": "error", "message": message or type(exc).__name__}

    def _log(self, message, level=Qgis.Info):
        QgsMessageLog.logMessage(message, LOG_TAG, level)
