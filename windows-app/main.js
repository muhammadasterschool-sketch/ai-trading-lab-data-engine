// AI Trading Lab — Data Engine · Windows shell (v4)
// Connects to your engine over LOCAL (computer) or CLOUD server.
const { app, BrowserWindow, ipcMain, dialog } = require('electron')
const path = require('path')
const fs = require('fs')

const CONFIG_PATH = () => path.join(app.getPath('userData'), 'config.json')

function loadConfig() {
  try {
    return JSON.parse(fs.readFileSync(CONFIG_PATH(), 'utf8'))
  } catch {
    return {}
  }
}

function saveConfig(cfg) {
  fs.mkdirSync(path.dirname(CONFIG_PATH()), { recursive: true })
  fs.writeFileSync(CONFIG_PATH(), JSON.stringify(cfg, null, 2))
}

/** Accepts "192.168.1.10:81", "http://x", "https://x" → normalized URL */
function normalizeUrl(raw) {
  let s = String(raw || '').trim()
  if (!s) return null
  if (!/^https?:\/\//i.test(s)) s = 'http://' + s
  s = s.replace(/\/+$/, '')
  const hostPart = s.replace(/^https?:\/\//i, '')
  if (!hostPart) return null
  if (!/^[A-Za-z0-9.\-_:]+$/.test(hostPart)) return null
  if (!/^https:\/\//i.test(s) && !hostPart.includes(':')) s += ':81'
  return s
}

let mainWindow = null

function createConnectWindow(prefillUrl, errorMessage) {
  const win = new BrowserWindow({
    width: 460,
    height: 700,
    resizable: true,
    backgroundColor: '#09090b',
    autoHideMenuBar: true,
    webPreferences: { contextIsolation: false, nodeIntegration: true }, // local trusted file only
  })
  win.loadFile(path.join(__dirname, 'connect.html'))
  win.once('did-finish-load', () => {
    if (prefillUrl) win.webContents.send('prefill', { url: prefillUrl, error: errorMessage || null })
  })
  ipcMain.removeAllListeners('connect')
  ipcMain.on('connect', (_e, rawUrl) => {
    const url = normalizeUrl(rawUrl)
    if (!url) {
      win.webContents.send('connect-error', 'Enter a valid address starting with http:// or https://')
      return
    }
    saveConfig({ server_url: url, connected_at: new Date().toISOString() })
    win.close()
    createMainWindow(url)
  })
  ipcMain.removeAllListeners('forget')
  ipcMain.on('forget', () => {
    saveConfig({})
    win.webContents.send('prefill', { url: '', error: null })
  })
}

function createMainWindow(url) {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    backgroundColor: '#09090b',
    autoHideMenuBar: true,
    show: false,
    title: 'AI Trading Lab — Data Engine',
  })
  mainWindow.loadURL(url).catch(() => {})
  mainWindow.once('ready-to-show', () => mainWindow.show())
  mainWindow.webContents.on('did-fail-load', (_e, code, desc, url2, isMain) => {
    if (!isMain) return
    if (mainWindow) {
      mainWindow.close()
      mainWindow = null
    }
    createConnectWindow(url, `Could not reach ${url} (${desc}). Check the server is running, then try again.`)
  })
  // Private deployment: allow self-signed certs on own cloud server
  mainWindow.webContents.on('certificate-error', (e, _url, _err, _cert, cb) => {
    e.preventDefault()
    cb(true)
  })
  mainWindow.on('closed', () => { mainWindow = null })
}

app.whenReady().then(() => {
  const cfg = loadConfig()
  if (cfg.server_url) {
    createMainWindow(cfg.server_url)
  } else {
    createConnectWindow('', '')
  }
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      const c = loadConfig()
      if (c.server_url) createMainWindow(c.server_url)
      else createConnectWindow('', '')
    }
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

// Single-instance lock (avoid multiple engines)
if (!app.requestSingleInstanceLock()) app.quit()
