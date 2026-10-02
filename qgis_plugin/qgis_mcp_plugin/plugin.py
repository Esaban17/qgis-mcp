"""Plugin de QGIS: socket local que ejecuta las órdenes del servidor MCP."""

import json

from qgis.PyQt.QtNetwork import QHostAddress, QTcpServer
from qgis.PyQt.QtWidgets import QAction
from qgis.core import Qgis, QgsMessageLog

from .handlers import CommandHandlers

HOST = "127.0.0.1"
PORT = 9876
LOG_TAG = "QGIS MCP"


class QgisMcpPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.server = None
        self.action = None
        self.handlers = CommandHandlers(iface)
        self._buffers = {}

    def initGui(self):
        self.action = QAction("QGIS MCP: iniciar servidor", self.iface.mainWindow())
        self.action.setCheckable(True)
        self.action.toggled.connect(self._toggle)
        self.iface.addPluginToMenu("QGIS MCP", self.action)
        self.iface.addToolBarIcon(self.action)

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
            return
        self.server = QTcpServer()
        if not self.server.listen(QHostAddress(HOST), PORT):
            self._log(f"No se pudo escuchar en {HOST}:{PORT}: {self.server.errorString()}", Qgis.Critical)
            self.server = None
            self.action.setChecked(False)
            return
        self.server.newConnection.connect(self._on_new_connection)
        self.action.setText("QGIS MCP: detener servidor")
        self._log(f"Escuchando en {HOST}:{PORT}")

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
        response = self._dispatch(line)
        sock.write((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
        sock.flush()
        sock.disconnectFromHost()

    def _dispatch(self, line):
        try:
            request = json.loads(line.decode("utf-8"))
            command = request.get("command")
            handler = self.handlers.get(command)
            if handler is None:
                return {"status": "error", "message": f"Orden desconocida: {command}"}
            result = handler(**(request.get("params") or {}))
            return {"status": "ok", "result": result}
        except Exception as exc:  # cualquier fallo vuelve al cliente como error
            self._log(f"Error ejecutando orden: {exc}", Qgis.Warning)
            return {"status": "error", "message": str(exc)}

    def _log(self, message, level=Qgis.Info):
        QgsMessageLog.logMessage(message, LOG_TAG, level)
