// DMVoiceChanger Web — shell de escritorio (Electron).
// Orquesta el servidor local Next.js (runtime\node.exe + app\arranque.cjs)
// y lo muestra en una VENTANA DE APLICACION propia: sin navegador, sin
// barras, con icono y ciclo de vida de programa de escritorio.
'use strict';

const { app, BrowserWindow, Menu, shell } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const http = require('http');

const RAIZ = path.resolve(__dirname, '..');
const APP_DIR = path.join(RAIZ, 'app');
const NODE_EXE = path.join(RAIZ, 'runtime', 'node.exe');
const PUERTO = 3987;
const URL_APP = 'http://127.0.0.1:' + PUERTO + '/';
const ESPERA_MAX_MS = 60000;

let ventana = null;
let servidor = null;
let apagando = false;

function logShell(msg) {
  try {
    const base = process.env.LOCALAPPDATA || app.getPath('home');
    fs.mkdirSync(path.join(base, 'DMVoiceWeb'), { recursive: true });
    fs.appendFileSync(path.join(base, 'DMVoiceWeb', 'error.log'),
      new Date().toISOString() + ' [shell] ' + msg + '\n');
  } catch (_) {}
}

function listo() {
  return new Promise(function (res) {
    const req = http.get(URL_APP, function (r) { r.resume(); res(true); });
    req.on('error', function () { res(false); });
    req.setTimeout(1500, function () { req.destroy(); res(false); });
  });
}

function arrancarServidor() {
  // arranque.cjs fija el entorno (puerto, HOSTNAME 127.0.0.1, DATABASE_URL
  // por usuario) y copia la plantilla de la DB al primer uso: nada que
  // duplicar aqui. Solo lo lanzamos y recogemos su stderr para diagnostico.
  servidor = spawn(NODE_EXE, [path.join(APP_DIR, 'arranque.cjs')], {
    cwd: APP_DIR,
    stdio: ['ignore', 'ignore', 'pipe'],
    windowsHide: true,
  });
  servidor.stderr.on('data', function (d) { logShell('servidor: ' + String(d)); });
  servidor.on('exit', function (codigo) {
    servidor = null;
    logShell('servidor termino con codigo ' + codigo);
    if (!apagando && ventana) {
      ventana.loadFile(path.join(__dirname, 'error.html')).catch(function () {});
    }
  });
}

function pararServidor() {
  apagando = true;
  if (servidor) {
    try { servidor.kill(); } catch (_) {}
    servidor = null;
  }
}

function crearVentana() {
  ventana = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 980,
    minHeight: 620,
    backgroundColor: '#1e150f',
    title: 'DMVoiceChanger Web — La Forja de Voces',
    icon: path.join(RAIZ, 'DMVoiceChanger.ico'),
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  ventana.loadFile(path.join(__dirname, 'cargando.html'));

  (async function () {
    const t0 = Date.now();
    while (!(await listo())) {
      if (Date.now() - t0 > ESPERA_MAX_MS) {
        ventana.loadFile(path.join(__dirname, 'error.html')).catch(function () {});
        return;
      }
      await new Promise(function (r) { setTimeout(r, 400); });
    }
    if (ventana && !apagando) ventana.loadURL(URL_APP);
  })();

  // Navegacion: la app vive aqui dentro; enlaces externos al navegador.
  ventana.webContents.setWindowOpenHandler(function (detalles) {
    if (detalles.url && detalles.url.indexOf(URL_APP) === 0) return { action: 'allow' };
    shell.openExternal(detalles.url);
    return { action: 'deny' };
  });
  ventana.webContents.on('will-navigate', function (e, url) {
    if (url.indexOf(URL_APP) !== 0) {
      e.preventDefault();
      shell.openExternal(url);
    }
  });

  ventana.on('closed', function () { ventana = null; });
}

// Una sola instancia: lanzar de nuevo trae la ventana al frente.
const unica = app.requestSingleInstanceLock();
if (!unica) {
  app.quit();
} else {
  app.on('second-instance', function () {
    if (ventana) {
      if (ventana.isMinimized()) ventana.restore();
      ventana.focus();
    }
  });

  app.whenReady().then(function () {
    Menu.setApplicationMenu(null);   // sin barra de menus: look de app, no de web
    arrancarServidor();
    crearVentana();
  });

  app.on('window-all-closed', function () {
    pararServidor();
    app.quit();
  });
  app.on('before-quit', pararServidor);
}
