#!/usr/bin/env python3
"""
Single-file PyQt6 + Flask + Paramiko Explorer with Draggable Splitters,
Custom Scrollbars, Enhanced File Previews, Database & Document Support,
and Improved Terminal & Upload Functionality.

Features (additional finishing touches):
- Smart file display: Hidden config files (e.g. .bashrc) and text files are shown in CodeMirror.
- Database file support: SQLite (.sqlite/.db) files are parsed and rendered as tables.
- DOC/DOCX support: Display a “preview not available” message with download options.
- Terminal enhancements:
   • Terminal input is fixed at the bottom.
   • Streaming endpoint (/terminal/stream/) handles long-running commands (e.g. “pm2 logs”) with ANSI-to-HTML conversion.
- File uploads now use XMLHttpRequest for per‑file progress with a visible progress bar.
- Various tweaks for better cross-platform and non‐blocking behavior.
"""

import os, sys

# FIX: Set the Qt platform for environments like Termux (where libEGL might be missing)
if sys.platform.startswith("linux") and os.environ.get("TERMUX"):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

import stat, time, threading, random, socket, io, re, tempfile, sqlite3
import paramiko
from flask import Flask, request, jsonify, send_file, render_template_string, Response
from werkzeug.serving import make_server
from ansi2html import Ansi2HTMLConverter


# ----------------- GLOBALS -----------------
global_ssh_client = None
global_sftp_client = None
flask_server = None
server_thread = None

app = Flask(__name__)

# ----------------- HTML TEMPLATE -----------------
# Note: Modifications include:
# • A theme selector and actions dropdown in the editor header.
# • Updated CSS so that the terminal output scrolls and the input stays fixed at the bottom.
# • Inclusion of ansi_up.js for ANSI conversion.
EXPLORER_TEMPLATE = r"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>VPS Explorer & Terminal</title>
  <!-- Bootstrap CSS -->
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.2.3/dist/css/bootstrap.min.css" rel="stylesheet"/>
  <!-- CodeMirror CSS -->
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.5/codemirror.min.css">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/6.65.7/theme/erlang-dark.min.css" />
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/6.65.7/theme/monokai.min.css" />
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/6.65.7/theme/rubyblue.min.css" />
  <!-- CodeMirror indent guides addon CSS -->
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.5/addon/display/indent-guide.min.css">
  <!-- Font Awesome for icons -->
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <!-- ansi_up for terminal ANSI conversion -->
  <script src="https://cdn.jsdelivr.net/npm/ansi-to-html@0.7.2/lib/ansi_to_html.bundle.min.js"></script>


  <script src="https://code.jquery.com/jquery-3.6.4.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.2.3/dist/js/bootstrap.bundle.min.js"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.5/codemirror.min.js"></script>
  <!-- CodeMirror modes -->
  <script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.5/mode/python/python.min.js"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.5/mode/javascript/javascript.min.js"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.5/mode/htmlmixed/htmlmixed.min.js"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.5/mode/css/css.min.js"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.5/mode/markdown/markdown.min.js"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.5/mode/xml/xml.min.js"></script>
  <!-- CodeMirror addon for indent guides -->
  <script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.5/addon/display/indent-guide.min.js"></script>

  <style>
    html, body {
      height: 100%;
      margin: 0;
      overflow: hidden;
      font-family: monospace;
    }
    /* Default dark theme colors */
    body.dark-mode {
      background-color: #000;
      color: #0ff;
    }
    /* Light theme override */
    body.light-mode {
      background-color: #fff;
      color: #000;
    }
    /* Scrollbar styling for WebKit */
    ::-webkit-scrollbar {
      width: 8px;
      height: 8px;
    }
    ::-webkit-scrollbar-track {
      background: #111;
    }
    ::-webkit-scrollbar-thumb {
      background-color: #0ff;
      border-radius: 4px;
    }
    ::-webkit-scrollbar-thumb:hover {
      background-color: #0cc;
    }
    /* Navigation Tabs */
    .nav-tabs .nav-link {
      background-color: #111;
      border: 1px solid #0ff;
      color: #0ff;
    }
    .nav-tabs .nav-link.active {
      background-color: #000;
      border-bottom-color: #000;
      color: #0ff;
    }
    /* Main container */
    .container-fluid {
      height: calc(100% - 45px);
      display: flex;
      flex-direction: column;
    }
    /* Explorer container: added splitter */
    #explorer-container {
      flex-grow: 1;
      overflow: hidden;
      display: flex;
      width: 100%;
    }
    .sidebar {
      width: 25%;
      border-right: 1px solid #0ff;
      overflow-y: auto;
      padding: 10px;
      box-sizing: border-box;
    }
    /* Draggable vertical splitter */
    #splitter-explorer {
      width: 5px;
      cursor: col-resize;
      background-color: #0ff;
    }
    .editor-container {
      width: 75%;
      display: flex;
      flex-direction: column;
      box-sizing: border-box;
    }
    .sidebar-header {
      font-size: 1.2em;
      padding-bottom: 10px;
      border-bottom: 1px solid #0ff;
      margin-bottom: 10px;
    }
    .tree-view {
      overflow-y: auto;
      max-height: calc(100% - 120px);
    }
    .actions-dropdown {
      margin: 10px;
    }
    .tree-view ul {
      list-style: none;
      margin: 0;
      padding-left: 20px;
      position: relative;
    }
    .tree-view ul::before {
      content: '';
      position: absolute;
      top: 0;
      left: 14px;
      bottom: 0;
      border-left: 0.5px solid grey;
      border-radius: 2px;
    }
    .tree-view li {
      margin: 0;
      position: relative;
      padding: 5px 0 5px 20px;
      color: wheat;
      font-size: large;
    }
    .tree-view li.selected > span {
      font-weight: bold;
      color: #ff0;
    }
    .file-explorer-item {
      cursor: pointer;
      align-items: center;
    }
    .file-explorer-item:hover {
      background-color: #111;
    }
    .editor-header {
      padding: 10px;
      border-bottom: 1px solid #0ff;
      display: flex;
      justify-content: space-between;
      background-color: #111;
      flex-shrink: 0;
      align-items: center;
    }
    .editor-content {
      flex-grow: 1;
      overflow: hidden;
      position: relative;
    }
    .CodeMirror {
      height: 100% !important;
      font-family: monospace;
    }
    /* Terminal container adjustments:
       - The terminal container is positioned relative.
       - The output area scrolls with a margin reserved for the input.
       - The terminal input is fixed at the bottom.
    */
    #terminal-container {
      position: relative;
      height: calc(100% - 45px);
      background-color: inherit;
      overflow: hidden;
    }
    #terminal-output {
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      bottom: 40px; /* reserve space for input */
      overflow-y: auto;
      border: 1px solid #0ff;
      padding: 10px;
      white-space: pre-wrap;
      background-color: inherit;
    }
    #terminal-input {
      position: absolute;
      bottom: 0;
      left: 0;
      right: 0;
      border: 1px solid #0ff;
      padding: 5px;
      font-family: monospace;
      box-sizing: border-box;
      background-color: inherit;
      color: inherit;
    }
    /* Upload progress styling */
    #uploadProgress {
      position: fixed;
      top: 20%;
      left: 50%;
      transform: translateX(-50%);
      width: 300px;
      z-index: 2000;
      display: none;
    }
  </style>
</head>
<body class="dark-mode">
  <!-- Navigation Tabs -->
  <ul class="nav nav-tabs">
    <li class="nav-item">
      <a class="nav-link active" id="tab-explorer" href="#">Explorer</a>
    </li>
    <li class="nav-item">
      <a class="nav-link" id="tab-terminal" href="#">Terminal</a>
    </li>
  </ul>

  <div class="container-fluid">
    <!-- Explorer Container with adjustable splitter -->
    <div id="explorer-container">
      <div class="sidebar">
        <div class="sidebar-header">VPS Explorer</div>
        <div class="tree-view" id="directoryTree">
          <!-- Directory tree will be built here -->
        </div>
        <div class="actions-dropdown dropdown">
          <button class="btn btn-sm btn-primary dropdown-toggle" type="button" data-bs-toggle="dropdown">
            Actions
          </button>
          <ul class="dropdown-menu">
            <li><a class="dropdown-item" href="#" id="createFileBtn">New File</a></li>
            <li><a class="dropdown-item" href="#" id="createFolderBtn">New Folder</a></li>
            <li><a class="dropdown-item" href="#" id="uploadFilesBtn">Upload Files</a></li>
            <li><a class="dropdown-item" href="#" id="deletePathBtn">Delete Selected</a></li>
            <li><a class="dropdown-item" href="#" id="downloadBtn">Download</a></li>
          </ul>
          <input type="file" id="uploadInput" multiple style="display:none;">
        </div>
      </div>
      <div id="splitter-explorer"></div>
      <div class="editor-container">
        <div class="editor-header">
          <span id="currentPath" class="fw-bold">No file selected</span>
          <span id="fileTypeTag" class="badge bg-secondary ms-2"></span>
          <button class="btn btn-sm btn-success" id="saveFileBtn">Save File</button>
          <!-- New Actions Dropdown in header for selected file/folder -->
          <div class="dropdown ms-3">
            <button class="btn btn-sm btn-info dropdown-toggle" type="button" id="actionDropdown" data-bs-toggle="dropdown" aria-expanded="false">
              Actions
            </button>
            <ul class="dropdown-menu" aria-labelledby="actionDropdown">
              <li><a class="dropdown-item" href="#" onclick="downloadFileAction()">Download</a></li>
              <li><a class="dropdown-item" href="#" onclick="deletePath()">Delete</a></li>
              <li><a class="dropdown-item" href="#" onclick="renameFileAction()">Rename</a></li>
            </ul>
          </div>
          <!-- Theme selection dropdown -->
          <select id="themeSelect" class="form-select form-select-sm ms-3" style="width:auto; display:inline-block;">
            <option value="rubyblue" selected>Ruby Blue (Dark)</option>
            <option value="monokai">Monokai (Dark)</option>
            <option value="erlang-dark">Erlang Dark (Dark)</option>
            <option value="default">Default (Light)</option>
          </select>
        </div>
        <div class="editor-content" id="editor-content">
          <textarea id="codeEditor"></textarea>
        </div>
      </div>
    </div>
    <!-- Terminal Container -->
    <div id="terminal-container">
      <div id="terminal-output"></div>
      <input type="text" id="terminal-input" placeholder="Type your command and hit Enter...">
    </div>
  </div>
  <!-- Upload Progress Bar -->
  <div id="uploadProgress" class="progress">
    <div id="uploadBar" class="progress-bar" role="progressbar" style="width: 0%;">0%</div>
  </div>
  <!-- CREATE ITEM MODAL (unchanged) -->
  <div class="modal fade" id="createItemModal" tabindex="-1" aria-hidden="true">
    <div class="modal-dialog modal-dialog-centered">
      <div class="modal-content" style="background-color:#111; color:#0ff;">
        <div class="modal-header">
          <h5 class="modal-title" id="createItemModalTitle"></h5>
          <button type="button" class="btn-close" data-bs-dismiss="modal" style="filter: invert(1);"></button>
        </div>
        <div class="modal-body">
          <p id="createItemModalText"></p>
          <div class="mb-2">
            <label for="createItemPath" class="form-label">Path (optional):</label>
            <input type="text" id="createItemPath" class="form-control" placeholder="Enter custom path or leave default">
          </div>
          <div class="mb-2">
            <label for="createItemName" class="form-label">Name:</label>
            <input type="text" id="createItemName" class="form-control" placeholder="Enter name...">
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary btn-sm" data-bs-dismiss="modal">Cancel</button>
          <button class="btn btn-primary btn-sm" id="createItemConfirmBtn">Create</button>
        </div>
      </div>
    </div>
  </div>

<script>
  // Global variables for Explorer
  let basePath = "/";
  let currentSelectedPath = null;
  let currentSelectedElement = null;
  let editor = null;
  let terminalPrompt = "vps@remote:~$ ";

  // Helper: decide if file should be opened in the text editor.
  // Now includes common hidden config files and recognized text extensions.
  function shouldOpenInEditor(path) {
    let lower = path.toLowerCase();
    const textExts = [".py", ".js", ".html", ".htm", ".css", ".md", ".xml", ".json", ".txt", ".sql", ".bashrc", ".bash_profile", ".profile", ".gitignore", ".env", ".ini", ".conf"];
    for (let ext of textExts) {
      if(lower.endsWith(ext)) return true;
    }
    return false;
  }

  document.addEventListener("DOMContentLoaded", function(){
    // Initialize CodeMirror editor for Explorer
    editor = CodeMirror.fromTextArea(document.getElementById("codeEditor"), {
      lineNumbers: true,
      mode: "markdown",
      theme: "rubyblue",
      indentWithTabs: true,
      indentUnit: 4,
      tabSize: 4,
      styleActiveLine: true,
      gutters: ["CodeMirror-linenumbers", "CodeMirror-foldgutter"],
      indentGuide: true
    });
    editor.setSize("100%", "100%");
    buildDirectoryTree(basePath, document.getElementById("directoryTree"));

    // Explorer button events
    document.getElementById("saveFileBtn").addEventListener("click", saveFile);
    document.getElementById("createFileBtn").addEventListener("click", ()=> openCreateModal("file"));
    document.getElementById("createFolderBtn").addEventListener("click", ()=> openCreateModal("folder"));
    document.getElementById("uploadFilesBtn").addEventListener("click", ()=> {
      if(!currentSelectedPath){
        alert("Select a directory first.");
        return;
      }
      let target = currentSelectedPath;
      if(!target.endsWith("/") && !target.endsWith("\\")) {
         // if a file is selected, use its parent
         target = parentDir(target);
      }
      document.getElementById("uploadInput").dataset.targetPath = target;
      document.getElementById("uploadInput").click();
    });
    document.getElementById("uploadInput").addEventListener("change", uploadFilesWithProgress);
    document.getElementById("deletePathBtn").addEventListener("click", deletePath);
    document.getElementById("downloadBtn").addEventListener("click", function(e){
      if(!currentSelectedPath){
        e.preventDefault();
        alert("Select a file/folder to download.");
      } else {
        this.href = "/download/?path=" + encodeURIComponent(currentSelectedPath);
      }
    });

    // Tab switching for Explorer/Terminal
    document.getElementById("tab-explorer").addEventListener("click", function(e){
      e.preventDefault();
      document.getElementById("explorer-container").style.display = "flex";
      document.getElementById("terminal-container").style.display = "block";
      document.querySelector("#tab-explorer").classList.add("active");
      document.querySelector("#tab-terminal").classList.remove("active");
    });
    document.getElementById("tab-terminal").addEventListener("click", function(e){
      e.preventDefault();
      document.getElementById("explorer-container").style.display = "none";
      document.getElementById("terminal-container").style.display = "block";
      document.querySelector("#tab-terminal").classList.add("active");
      document.querySelector("#tab-explorer").classList.remove("active");
      let termOut = document.getElementById("terminal-output");
      if(termOut.innerHTML.trim() === ""){
        termOut.innerHTML += terminalPrompt;
      }
    });

    // Terminal input handler
    document.getElementById("terminal-input").addEventListener("keydown", function(e){
      if(e.key === "Enter"){
        e.preventDefault();
        let cmd = this.value.trim();
        if(cmd === "") return;
        appendToTerminal("\n" + cmd + "\n");
        // For long-running commands (e.g., pm2 logs) use stream
        if(cmd.startsWith("pm2 logs")) {
          executeTerminalCommandStream(cmd);
        } else {
          executeTerminalCommand(cmd);
        }
        this.value = "";
      }
    });

    // Theme selection handler
    document.getElementById("themeSelect").addEventListener("change", function() {
      var theme = this.value;
      editor.setOption("theme", theme);
      if(theme === "default"){
         document.body.classList.remove("dark-mode");
         document.body.classList.add("light-mode");
      } else {
         document.body.classList.remove("light-mode");
         document.body.classList.add("dark-mode");
      }
    });

    // Set up splitter for Explorer (vertical)
    const splitterExplorer = document.getElementById("splitter-explorer");
    const sidebar = document.querySelector(".sidebar");
    const editorContainer = document.querySelector(".editor-container");
    splitterExplorer.addEventListener("mousedown", function(e) {
      e.preventDefault();
      document.addEventListener("mousemove", onDragExplorer);
      document.addEventListener("mouseup", stopDragExplorer);
    });
    function onDragExplorer(e) {
      const containerRect = document.getElementById("explorer-container").getBoundingClientRect();
      let newSidebarWidth = e.clientX - containerRect.left;
      if(newSidebarWidth < 100) newSidebarWidth = 100;
      if(newSidebarWidth > containerRect.width - 100) newSidebarWidth = containerRect.width - 100;
      sidebar.style.width = newSidebarWidth + "px";
      editorContainer.style.width = (containerRect.width - newSidebarWidth - splitterExplorer.offsetWidth) + "px";
    }
    function stopDragExplorer(e) {
      document.removeEventListener("mousemove", onDragExplorer);
      document.removeEventListener("mouseup", stopDragExplorer);
    }
  });

  // Append text to terminal output with ANSI conversion
    function appendToTerminal(htmlText) {
    let termOut = document.getElementById("terminal-output");
    termOut.innerHTML += htmlText;
    termOut.scrollTop = termOut.scrollHeight;
  }



  // Execute terminal command (non-streaming)
  async function executeTerminalCommand(cmd) {
    let fd = new FormData();
    fd.append("command", cmd);
    try {
      let res = await fetch("/terminal/execute/", { method:"POST", body: fd });
      let data = await res.json();
      if(data.status === "ok"){
        appendToTerminal(data.output + "\n" + terminalPrompt);
      } else {
        appendToTerminal("Error: " + data.message + "\n" + terminalPrompt);
      }
    } catch(err) {
      appendToTerminal("Request failed: " + err + "\n" + terminalPrompt);
    }
  }

  // Execute terminal command using streaming (for long-running commands)
  async function executeTerminalCommandStream(cmd) {
    let fd = new FormData();
    fd.append("command", cmd);
    try {
      let response = await fetch("/terminal/stream/", { method:"POST", body: fd });
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      function read() {
        reader.read().then(({ done, value }) => {
          if (done) {
            appendToTerminal("\n" + terminalPrompt);
            return;
          }
          // Directly append the HTML (already converted by ansi2html on the server)
          appendToTerminal(decoder.decode(value));
          read();
        });
      }
      read();
    } catch(err) {
      appendToTerminal("Stream failed: " + err + "\n" + terminalPrompt);
    }
  }


  // Format file sizes
  function formatSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    let kb = bytes / 1024;
    if (kb < 1024) return kb.toFixed(2) + " KB";
    let mb = kb / 1024;
    if (mb < 1024) return mb.toFixed(2) + " MB";
    let gb = mb / 1024;
    return gb.toFixed(2) + " GB";
  }

  // Determine CodeMirror mode from file extension
  function detectModeFromExtension(filePath) {
    let path = filePath.toLowerCase();
    let mode = "null", fileType = "Plain Text";
    if(path.endsWith(".py")){
      mode = "python";
      fileType = "Python";
    } else if(path.endsWith(".js")){
      mode = "javascript";
      fileType = "JavaScript";
    } else if(path.endsWith(".html") || path.endsWith(".htm")){
      mode = "htmlmixed";
      fileType = "HTML";
    } else if(path.endsWith(".css")){
      mode = "css";
      fileType = "CSS";
    } else if(path.endsWith(".md")){
      mode = "markdown";
      fileType = "Markdown";
    } else if(path.endsWith(".xml")){
      mode = "xml";
      fileType = "XML";
    } else if(path.endsWith(".json")){
      mode = "javascript";
      fileType = "JSON";
    } else if(path.endsWith(".sql")){
      mode = "sql";
      fileType = "SQL";
    }
    return { mode, fileType };
  }

  // Load file content and update CodeMirror or alternative display
  async function loadFileContents(path) {
    currentSelectedPath = path;
    document.getElementById("currentPath").textContent = path;
    let lower = path.toLowerCase();
    // For SQLite database files, use the dedicated endpoint
    if(lower.endsWith(".sqlite") || lower.endsWith(".db")){
      let res = await fetch("/ajax/sqlite/?path=" + encodeURIComponent(path));
      let data = await res.json();
      if(data.status === "ok"){
        let html = "<h5>SQLite Database Preview</h5>";
        for(let table in data.data) {
          html += "<h6>" + table + "</h6>";
          let tdata = data.data[table];
          html += "<table class='table table-sm table-bordered'><thead><tr>";
          tdata.columns.forEach(col => { html += "<th>" + col + "</th>"; });
          html += "</tr></thead><tbody>";
          tdata.rows.forEach(row => {
            html += "<tr>";
            row.forEach(cell => { html += "<td>" + cell + "</td>"; });
            html += "</tr>";
          });
          html += "</tbody></table>";
        }
        document.getElementById("editor-content").innerHTML = html;
        document.getElementById("fileTypeTag").textContent = "SQLite DB";
      } else {
        alert(data.message || "Error loading database file.");
      }
    }
    // DOC/DOCX files: show message (preview not available)
    else if(lower.endsWith(".doc") || lower.endsWith(".docx")){
      let html = "<div class='alert alert-info'>Preview not available for DOC/DOCX files.</div>";
      html += "<button class='btn btn-sm btn-primary' onclick='downloadFileAction()'>Download</button>";
      document.getElementById("editor-content").innerHTML = html;
      document.getElementById("fileTypeTag").textContent = "Document";
    }
    else if (shouldOpenInEditor(path)) {
      // For text files, load via AJAX and display in CodeMirror
      let url = "/ajax/file/?path=" + encodeURIComponent(path);
      let res = await fetch(url);
      let data = await res.json();
      if(data.status === 'ok'){
        document.getElementById("editor-content").innerHTML = '<textarea id="codeEditor"></textarea>';
        editor = CodeMirror.fromTextArea(document.getElementById("codeEditor"), {
          lineNumbers: true,
          mode: "markdown",
          theme: document.getElementById("themeSelect").value,
          indentWithTabs: true,
          indentUnit: 4,
          tabSize: 4,
          styleActiveLine: true,
          gutters: ["CodeMirror-linenumbers", "CodeMirror-foldgutter"],
          indentGuide: true
        });
        editor.setValue(data.content);
        let { mode, fileType } = detectModeFromExtension(path);
        editor.setOption("mode", mode);
        document.getElementById("fileTypeTag").textContent = fileType;
      } else {
        alert(data.message || "Error loading file.");
      }
    } else {
      // For non-text files (images, PDFs, videos, etc.)
      let editorContent = document.getElementById("editor-content");
      if(lower.endsWith(".png") || lower.endsWith(".jpg") || lower.endsWith(".jpeg") || lower.endsWith(".gif") || lower.endsWith(".bmp") || lower.endsWith(".svg")){
         editorContent.innerHTML = "<img src='/download/?path=" + encodeURIComponent(path) + "&inline=1' style='max-width:100%; max-height:100%;'/>";
      } else if(lower.endsWith(".pdf")){
         editorContent.innerHTML = "<iframe src='/download/?path=" + encodeURIComponent(path) + "&inline=1' style='width:100%; height:100%; border:none;'></iframe>";
      } else if(lower.endsWith(".mp4") || lower.endsWith(".avi") || lower.endsWith(".mov") || lower.endsWith(".wmv") || lower.endsWith(".flv")){
         editorContent.innerHTML = "<video controls style='width:100%; height:100%;'><source src='/download/?path=" + encodeURIComponent(path) + "&inline=1'></video>";
      } else {
         let message = "<div class='alert alert-info'>Cannot display this file type in the editor.</div>";
         message += "<button class='btn btn-sm btn-primary' onclick='downloadFileAction()'>Download</button> ";
         message += "<button class='btn btn-sm btn-danger' onclick='deletePath()'>Delete</button> ";
         message += "<button class='btn btn-sm btn-warning' onclick='renameFileAction()'>Rename</button>";
         editorContent.innerHTML = message;
         if(editor) { editor.toTextArea(); editor = null; }
         document.getElementById("fileTypeTag").textContent = "";
       }
    }
  }

  // Build directory tree recursively (unchanged)
  function buildDirectoryTree(path, container) {
    container.innerHTML = "";
    fetch("/ajax/list/?path=" + encodeURIComponent(path))
    .then(r=>r.json())
    .then(data=>{
      if(data.status === 'ok'){
        let ul = document.createElement("ul");
        container.appendChild(ul);
        data.directories.forEach(dir => {
          let li = document.createElement("li");
          li.classList.add("file-explorer-item");
          let toggleIcon = document.createElement("i");
          toggleIcon.className = "fas fa-caret-right me-1";
          toggleIcon.style.cursor = "pointer";
          toggleIcon.addEventListener("click", function(e) {
            e.stopPropagation();
            toggleDirectory(li, dir.path, toggleIcon);
          });
          li.appendChild(toggleIcon);
          let folderIcon = document.createElement("i");
          folderIcon.className = "fas fa-folder me-1";
          li.appendChild(folderIcon);
          let span = document.createElement("span");
          span.textContent = dir.name;
          span.addEventListener("click", function(e) {
            e.stopPropagation();
            selectPath(dir.path, li);
          });
          li.appendChild(span);
          ul.appendChild(li);
        });
        data.files.forEach(file => {
          let li = document.createElement("li");
          li.classList.add("file-explorer-item");
          let spacer = document.createElement("span");
          spacer.style.display = "inline-block";
          spacer.style.width = "20px";
          li.appendChild(spacer);
          let fileIcon = document.createElement("i");
          fileIcon.className = "fas fa-file me-1";
          li.appendChild(fileIcon);
          let span = document.createElement("span");
          span.textContent = file.name;
          span.title = "Size: " + formatSize(file.size);
          span.addEventListener("click", function(e) {
            e.stopPropagation();
            selectPath(file.path, li);
            loadFileContents(file.path);
          });
          li.appendChild(span);
          ul.appendChild(li);
        });
      } else {
        container.innerHTML = "<p class='text-danger'>" + data.message + "</p>";
      }
    })
    .catch(err=>{
      container.innerHTML = "<p class='text-danger'>Error: " + err + "</p>";
    });
  }

  // Toggle directory expansion (unchanged)
  function toggleDirectory(li, dirPath, toggleIcon) {
    let existingUl = li.querySelector("ul");
    if(existingUl) {
      if(existingUl.style.display === "none" || existingUl.style.display === ""){
        existingUl.style.display = "block";
        toggleIcon.className = "fas fa-caret-down me-1";
      } else {
        existingUl.style.display = "none";
        toggleIcon.className = "fas fa-caret-right me-1";
      }
    } else {
      let nestedUl = document.createElement("ul");
      li.appendChild(nestedUl);
      fetch("/ajax/list/?path=" + encodeURIComponent(dirPath))
      .then(r=>r.json())
      .then(data=>{
        if(data.status === 'ok'){
          data.directories.forEach(dir=>{
            let childLi = document.createElement("li");
            childLi.classList.add("file-explorer-item");
            let childToggleIcon = document.createElement("i");
            childToggleIcon.className = "fas fa-caret-right me-1";
            childToggleIcon.style.cursor = "pointer";
            childToggleIcon.addEventListener("click", (e)=>{
              e.stopPropagation();
              toggleDirectory(childLi, dir.path, childToggleIcon);
            });
            childLi.appendChild(childToggleIcon);
            let folderIcon = document.createElement("i");
            folderIcon.className = "fas fa-folder me-1";
            childLi.appendChild(folderIcon);
            let span = document.createElement("span");
            span.textContent = dir.name;
            span.addEventListener("click", (e)=>{
              e.stopPropagation();
              selectPath(dir.path, childLi);
            });
            childLi.appendChild(span);
            nestedUl.appendChild(childLi);
          });
          data.files.forEach(file=>{
            let childLi = document.createElement("li");
            childLi.classList.add("file-explorer-item");
            let spacer = document.createElement("span");
            spacer.style.display = "inline-block";
            spacer.style.width = "20px";
            childLi.appendChild(spacer);
            let fileIcon = document.createElement("i");
            fileIcon.className = "fas fa-file me-1";
            childLi.appendChild(fileIcon);
            let span = document.createElement("span");
            span.textContent = file.name;
            span.title = "Size: " + formatSize(file.size);
            span.addEventListener("click", (e)=>{
              e.stopPropagation();
              selectPath(file.path, childLi);
              loadFileContents(file.path);
            });
            childLi.appendChild(span);
            nestedUl.appendChild(childLi);
          });
          nestedUl.style.display = "block";
          toggleIcon.className = "fas fa-caret-down me-1";
        } else {
          nestedUl.innerHTML = "<li class='text-danger'>" + data.message + "</li>";
        }
      })
      .catch(err=>{
        nestedUl.innerHTML = "<li class='text-danger'>Error: " + err + "</li>";
      });
    }
  }

  // Mark selected path and update header
  function selectPath(path, element) {
    currentSelectedPath = path;
    document.getElementById("currentPath").textContent = path;
    document.querySelectorAll("#directoryTree li.selected").forEach(el => el.classList.remove("selected"));
    if(element) {
      element.classList.add("selected");
      currentSelectedElement = element;
    }
  }

  function parentDir(path){
    if(path === "/" || path === "\\" || /^[A-Za-z]:\\?$/.test(path)) return path;
    return path.replace(/[\\/]+[^\\/]+[\\/]?$/, '');
  }
  function isDirPath(path){
    return path.endsWith("/") || path.endsWith("\\");
  }

  // Save file (unchanged)
  function saveFile(){
    if(!currentSelectedPath){
      alert("Select a file first!");
      return;
    }
    if(isDirPath(currentSelectedPath)){
      alert("This is a directory, cannot save!");
      return;
    }
    if(!confirm("Save changes to file:\n" + currentSelectedPath + "?")){
      return;
    }
    let content = editor.getValue();
    let fd = new FormData();
    fd.append("path", currentSelectedPath);
    fd.append("content", content);
    fetch("/ajax/save/", { method:"POST", body: fd })
    .then(r=>r.json())
    .then(data=>{
      if(data.status === 'ok'){
        alert("File saved successfully.");
      } else {
        alert("Error: " + data.message);
      }
    })
    .catch(err=>{
      alert("Failed to save: " + err);
    });
  }

  // Delete path (unchanged)
  function deletePath(){
    if(!currentSelectedPath){
      alert("Select a file/folder first.");
      return;
    }
    let type = isDirPath(currentSelectedPath) ? "folder" : "file";
    if(!confirm("Are you sure you want to delete the following " + type + "?\n\n" + currentSelectedPath)){
      return;
    }
    let fd = new FormData();
    fd.append("path", currentSelectedPath);
    fetch("/ajax/delete/", { method:"POST", body: fd })
    .then(r=>r.json())
    .then(data=>{
      if(data.status === 'ok'){
        alert("Deleted successfully: " + currentSelectedPath);
        buildDirectoryTree(basePath, document.getElementById("directoryTree"));
        if(!isDirPath(currentSelectedPath)){
          if(editor){ editor.setValue(""); }
          document.getElementById("fileTypeTag").textContent = "";
          document.getElementById("currentPath").textContent = "";
        }
        currentSelectedPath = null;
      } else {
        alert("Error: " + data.message);
      }
    })
    .catch(err=>{
      alert("Error: " + err);
    });
  }

  // Modal for creating files/folders (unchanged)
  function openCreateModal(type){
    if(!currentSelectedPath){
      alert("Select a directory first!");
      return;
    }
    let modalEl = document.getElementById("createItemModal");
    let bsModal = new bootstrap.Modal(modalEl);
    let defaultPath = isDirPath(currentSelectedPath) ? currentSelectedPath : parentDir(currentSelectedPath);
    document.getElementById("createItemModalTitle").textContent = (type === 'folder' ? "Create Folder" : "Create File");
    document.getElementById("createItemModalText").textContent = "Create a new " + type + " in: " + defaultPath;
    document.getElementById("createItemName").value = "";
    document.getElementById("createItemPath").value = defaultPath;
    bsModal.show();
    document.getElementById("createItemConfirmBtn").onclick = function(){
      let name = document.getElementById("createItemName").value.trim();
      let customPath = document.getElementById("createItemPath").value.trim() || defaultPath;
      if(!name){
        alert("Enter a name!");
        return;
      }
      createItem(customPath, name, type);
      bsModal.hide();
    };
  }

  // Create item (file/folder) (unchanged)
  function createItem(parent, name, type){
    let fd = new FormData();
    fd.append("parent_path", parent);
    fd.append("name", name);
    fd.append("type", type);
    fetch("/ajax/new_item/", { method:"POST", body: fd })
    .then(r=>r.json())
    .then(data=>{
      if(data.status === 'ok'){
        alert(data.message + "\nCreated at: " + parent);
        buildDirectoryTree(basePath, document.getElementById("directoryTree"));
      } else {
        alert("Error: " + data.message);
      }
    })
    .catch(err=>{
      alert("Error: " + err);
    });
  }

  // Upload files using XMLHttpRequest with progress events
  function uploadFilesWithProgress(){
    let files = this.files;
    if(!files || files.length === 0) return;
    let target = this.dataset.targetPath;
    let progressDiv = document.getElementById("uploadProgress");
    let progressBar = document.getElementById("uploadBar");
    progressDiv.style.display = "block";
    let totalFiles = files.length, uploaded = 0;
    function uploadSingle(file, index, callback) {
      let xhr = new XMLHttpRequest();
      xhr.open("POST", "/ajax/upload/");
      xhr.upload.addEventListener("progress", function(e) {
         if(e.lengthComputable){
           let percent = Math.round((e.loaded / e.total) * 100);
           progressBar.style.width = percent + "%";
           progressBar.innerHTML = percent + "%";
         }
      });
      xhr.onreadystatechange = function() {
        if(xhr.readyState === 4) {
          uploaded++;
          callback();
        }
      };
      let fd = new FormData();
      fd.append("parent_path", target);
      fd.append("file_0", file);
      xhr.send(fd);
    }
    function uploadNext(i) {
      if(i >= totalFiles) {
        alert("All files uploaded.");
        progressDiv.style.display = "none";
        buildDirectoryTree(basePath, document.getElementById("directoryTree"));
        return;
      }
      uploadSingle(files[i], i, function() {
        uploadNext(i+1);
      });
    }
    uploadNext(0);
  }

  // Action functions for non-text files
  function downloadFileAction() {
    if(currentSelectedPath){
      window.location.href = "/download/?path=" + encodeURIComponent(currentSelectedPath);
    }
  }

  function renameFileAction() {
    if(!currentSelectedPath){
      alert("No file selected!");
      return;
    }
    let parts = currentSelectedPath.split("/");
    let currentName = parts[parts.length-1];
    let newName = prompt("Enter new name for the file/folder:", currentName);
    if(newName){
      let fd = new FormData();
      fd.append("old_path", currentSelectedPath);
      fd.append("new_name", newName);
      fetch("/ajax/rename/", { method:"POST", body: fd })
      .then(r=>r.json())
      .then(data=>{
        if(data.status === "ok"){
          alert("Renamed successfully.");
          buildDirectoryTree(basePath, document.getElementById("directoryTree"));
        } else {
          alert("Error: " + data.message);
        }
      })
      .catch(err=>{
        alert("Rename failed: " + err);
      });
    }
  }
</script>
</body>
</html>
"""

# ----------------- FLASK ROUTES -----------------
@app.route("/")
def index():
    return render_template_string(EXPLORER_TEMPLATE)

def sanitize_path(path: str) -> str:
    return path.replace("\\", "/")

def format_size(sz: int) -> int:
    return sz if sz >= 0 else 0

@app.route("/ajax/list/", methods=["GET"])
def ajax_list():
    if not global_sftp_client:
        return jsonify(status="error", message="SFTP client not connected!")
    path = request.args.get("path", "/")
    try:
        attrs = global_sftp_client.listdir_attr(path)
    except Exception as e:
        return jsonify(status="error", message=str(e))
    dirs, files = [], []
    for a in attrs:
        full_path = sanitize_path(os.path.join(path, a.filename))
        is_dir = stat.S_ISDIR(a.st_mode)
        item = {"name": a.filename, "path": full_path, "size": format_size(a.st_size)}
        (dirs if is_dir else files).append(item)
    dirs.sort(key=lambda x: x["name"].lower())
    files.sort(key=lambda x: x["name"].lower())
    return jsonify(status="ok", directories=dirs, files=files)

@app.route("/ajax/file/", methods=["GET"])
def ajax_file():
    if not global_sftp_client:
        return jsonify(status="error", message="SFTP client not connected!")
    path = request.args.get("path", "")
    if not path:
        return jsonify(status="error", message="No path provided")
    try:
        with global_sftp_client.open(path, "r") as f:
            content = f.read().decode("utf-8", errors="replace")
        return jsonify(status="ok", content=content)
    except Exception as e:
        return jsonify(status="error", message=str(e))

@app.route("/ajax/save/", methods=["POST"])
def ajax_save():
    if not global_sftp_client:
        return jsonify(status="error", message="SFTP client not connected!")
    path = request.form.get("path", "")
    content = request.form.get("content", "")
    if not path:
        return jsonify(status="error", message="No path provided")
    try:
        with global_sftp_client.open(path, "w") as f:
            f.write(content.encode("utf-8"))
        return jsonify(status="ok", message="File saved")
    except Exception as e:
        return jsonify(status="error", message=str(e))

@app.route("/ajax/delete/", methods=["POST"])
def ajax_delete():
    if not global_sftp_client:
        return jsonify(status="error", message="SFTP client not connected!")
    path = request.form.get("path", "")
    if not path:
        return jsonify(status="error", message="No path provided")
    try:
        st = global_sftp_client.stat(path)
        if stat.S_ISDIR(st.st_mode):
            def delete_dir(p):
                for i in global_sftp_client.listdir_attr(p):
                    sp = sanitize_path(os.path.join(p, i.filename))
                    if stat.S_ISDIR(i.st_mode):
                        delete_dir(sp)
                    else:
                        global_sftp_client.remove(sp)
                global_sftp_client.rmdir(p)
            delete_dir(path)
        else:
            global_sftp_client.remove(path)
        return jsonify(status="ok", message="Deleted")
    except Exception as e:
        return jsonify(status="error", message=str(e))

@app.route("/ajax/new_item/", methods=["POST"])
def ajax_new_item():
    if not global_sftp_client:
        return jsonify(status="error", message="SFTP not connected!")
    parent_path = request.form.get("parent_path", "")
    name = request.form.get("name", "")
    item_type = request.form.get("type", "file")
    if not parent_path or not name:
        return jsonify(status="error", message="Missing parameters")
    try:
        st = global_sftp_client.stat(parent_path)
        if not stat.S_ISDIR(st.st_mode):
            parent_path = os.path.dirname(parent_path)
    except:
        pass
    full_path = sanitize_path(os.path.join(parent_path, name))
    try:
        if item_type == "folder":
            global_sftp_client.mkdir(full_path)
        else:
            with global_sftp_client.open(full_path, "w") as f:
                f.write(b"")
        return jsonify(status="ok", message=f"{item_type.capitalize()} created")
    except Exception as e:
        return jsonify(status="error", message=str(e))

@app.route("/ajax/upload/", methods=["POST"])
def ajax_upload():
    if not global_sftp_client:
        return jsonify(status="error", message="SFTP not connected!")
    parent_path = request.form.get("parent_path", "")
    if not parent_path:
        return jsonify(status="error", message="No parent path provided")
    try:
        st = global_sftp_client.stat(parent_path)
        if not stat.S_ISDIR(st.st_mode):
            parent_path = os.path.dirname(parent_path)
    except:
        pass
    # Expect only one file per request (the progress uploader sends one file at a time)
    for key in request.files.keys():
        f = request.files[key]
        if f:
            temp_path = tempfile.mktemp()
            f.save(temp_path)
            remote_path = sanitize_path(os.path.join(parent_path, f.filename))
            try:
                global_sftp_client.put(temp_path, remote_path)
            except Exception as e:
                return jsonify(status="error", message=str(e))
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            break
    return jsonify(status="ok", message="File uploaded")

@app.route("/download/", methods=["GET"])
def download_file():
    if not global_sftp_client:
        return "SFTP not connected!", 500
    path = request.args.get("path", "")
    if not path:
        return "No path provided", 400
    inline = request.args.get("inline", "0") == "1"
    try:
        st = global_sftp_client.stat(path)
        if stat.S_ISDIR(st.st_mode):
            import zipfile
            tmp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
            tmp_zip.close()
            def add_dir_to_zip(sftp, remote_path, zip_path):
                for attr in sftp.listdir_attr(remote_path):
                    remote_item = os.path.join(remote_path, attr.filename).replace("\\", "/")
                    zip_item = os.path.join(zip_path, attr.filename)
                    if stat.S_ISDIR(attr.st_mode):
                        add_dir_to_zip(sftp, remote_item, zip_item)
                    else:
                        with sftp.open(remote_item, "rb") as file_obj:
                            data = file_obj.read()
                        zipf.writestr(zip_item, data)
            with zipfile.ZipFile(tmp_zip.name, "w", zipfile.ZIP_DEFLATED) as zipf:
                add_dir_to_zip(global_sftp_client, path, os.path.basename(path))
            return send_file(tmp_zip.name, as_attachment=not inline, download_name=os.path.basename(path) + ".zip")
        else:
            tmpf = tempfile.NamedTemporaryFile(delete=False)
            global_sftp_client.get(path, tmpf.name)
            tmpf.close()
            return send_file(tmpf.name, as_attachment=not inline, download_name=os.path.basename(path))
    except Exception as e:
        return str(e), 500

# New route: Terminal command execution (non-streaming)
@app.route("/terminal/execute/", methods=["POST"])
def terminal_execute():
    if not global_ssh_client:
        return jsonify(status="error", message="SSH not connected!")
    cmd = request.form.get("command", "")
    if not cmd:
        return jsonify(status="error", message="No command provided")
    try:
        stdin, stdout, stderr = global_ssh_client.exec_command(cmd)
        # Read the command output
        output = stdout.read().decode("utf-8") + stderr.read().decode("utf-8")
        # Convert ANSI to HTML
        conv = Ansi2HTMLConverter(inline=True)
        html = conv.convert(output, full=False)
        return jsonify(status="ok", output=html)
    except Exception as e:
        return jsonify(status="error", message=str(e))

# New route: Terminal streaming endpoint for long-running commands
@app.route("/terminal/stream/", methods=["POST"])
def terminal_stream():
    if not global_ssh_client:
        return jsonify(status="error", message="SSH not connected!")
    cmd = request.form.get("command", "")
    if not cmd:
        return jsonify(status="error", message="No command provided")
    # Create a new converter instance for this stream
    conv = Ansi2HTMLConverter(inline=True)
    def generate():
        try:
            transport = global_ssh_client.get_transport()
            channel = transport.open_session()
            channel.exec_command(cmd)
            while True:
                if channel.recv_ready():
                    data = channel.recv(1024)
                    if not data:
                        break
                    chunk = data.decode("utf-8", errors="replace")
                    # Convert the received chunk to HTML
                    html_chunk = conv.convert(chunk, full=False)
                    yield html_chunk
                if channel.exit_status_ready():
                    break
                time.sleep(0.1)
            # Optionally yield any final conversion output here if needed
        except Exception as e:
            yield "<br>Error: " + str(e)
    return Response(generate(), mimetype="text/html")


# New route: SQLite database preview endpoint
@app.route("/ajax/sqlite/", methods=["GET"])
def ajax_sqlite():
    if not global_sftp_client:
        return jsonify(status="error", message="SFTP client not connected!")
    path = request.args.get("path", "")
    if not path:
        return jsonify(status="error", message="No path provided")
    try:
        tmpf = tempfile.NamedTemporaryFile(delete=False)
        tmpf.close()
        global_sftp_client.get(path, tmpf.name)
        conn = sqlite3.connect(tmpf.name)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cur.fetchall()
        data = {}
        for table in tables:
            table_name = table[0]
            cur.execute(f"SELECT * FROM {table_name} LIMIT 10;")
            rows = cur.fetchall()
            cur.execute(f"PRAGMA table_info({table_name});")
            columns = [info[1] for info in cur.fetchall()]
            data[table_name] = {"columns": columns, "rows": rows}
        conn.close()
        os.remove(tmpf.name)
        return jsonify(status="ok", data=data)
    except Exception as e:
        return jsonify(status="error", message=str(e))

# New route: Rename file/folder (unchanged from previous version)
@app.route("/ajax/rename/", methods=["POST"])
def ajax_rename():
    if not global_sftp_client:
        return jsonify(status="error", message="SFTP not connected!")
    old_path = request.form.get("old_path", "")
    new_name = request.form.get("new_name", "")
    if not old_path or not new_name:
        return jsonify(status="error", message="Missing parameters")
    new_path = sanitize_path(os.path.join(os.path.dirname(old_path), new_name))
    try:
        global_sftp_client.rename(old_path, new_path)
        return jsonify(status="ok", message="Renamed successfully")
    except Exception as e:
        return jsonify(status="error", message=str(e))

# ----------------- START/STOP SERVER -----------------
def start_flask_server(port):
    global flask_server
    flask_server = make_server("0.0.0.0", port, app)
    flask_server.serve_forever()

# ----------------- PYQT DIALOGS -----------------
from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton
)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QPixmap, QDesktopServices
import qrcode

class LoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VPS Credentials")
        self.setFixedSize(300, 250)
        layout = QVBoxLayout()
        self.ip_edit = QLineEdit()
        self.ip_edit.setPlaceholderText("IP Address (e.g. 1.2.3.4)")
        self.port_edit = QLineEdit()
        self.port_edit.setPlaceholderText("Port (22)")
        self.port_edit.setText("22")
        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText("Username")
        self.user_edit.setText("root")
        self.pass_edit = QLineEdit()
        self.pass_edit.setPlaceholderText("Password")
        self.pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(QLabel("Enter VPS Credentials:"))
        layout.addWidget(self.ip_edit)
        layout.addWidget(self.port_edit)
        layout.addWidget(self.user_edit)
        layout.addWidget(self.pass_edit)
        self.status_label = QLabel("")
        layout.addWidget(self.status_label)
        btn_layout = QHBoxLayout()
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.do_connect)
        btn_layout.addWidget(self.connect_btn)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)
        self.setLayout(layout)
    def do_connect(self):
        ip = self.ip_edit.text().strip()
        port = self.port_edit.text().strip() or "22"
        user = self.user_edit.text().strip()
        pw = self.pass_edit.text().strip()
        if not ip or not user or not pw:
            self.status_label.setText("All fields required!")
            return
        self.status_label.setText("Connecting...")
        self.repaint()
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(ip, int(port), user, pw, timeout=10)
            sftp = ssh.open_sftp()
            global global_ssh_client, global_sftp_client
            global_ssh_client = ssh
            global_sftp_client = sftp
            self.accept()
        except Exception as e:
            self.status_label.setText("Connection failed: " + str(e))

class ControlDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Explorer Control")
        self.setFixedSize(350, 500)
        self.server_port = None
        self.server_running = False
        layout = QVBoxLayout()
        self.info_label = QLabel("Ready. Please click 'Start' to launch the Flask server.")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.info_label)
        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.qr_label)
        self.url_label = QLabel("")
        self.url_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.url_label)
        self.open_btn = QPushButton("Open in Browser")
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self.open_in_browser)
        layout.addWidget(self.open_btn)
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("Start")
        self.start_btn.clicked.connect(self.start_server)
        btn_layout.addWidget(self.start_btn)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_server)
        btn_layout.addWidget(self.stop_btn)
        self.restart_btn = QPushButton("Restart")
        self.restart_btn.setEnabled(False)
        self.restart_btn.clicked.connect(self.restart_server)
        btn_layout.addWidget(self.restart_btn)
        layout.addLayout(btn_layout)
        self.setLayout(layout)
    def start_server(self):
        global server_thread
        if self.server_running:
            return
        if not global_sftp_client or not global_ssh_client:
            self.info_label.setText("Error: SSH not connected.")
            return
        port = random.randint(5000, 9999)
        self.server_port = port
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
        except:
            local_ip = "127.0.0.1"
        finally:
            s.close()
        url = f"http://{local_ip}:{port}/"
        self.url_label.setText(url)
        qr = qrcode.QRCode(box_size=4, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        pixmap = QPixmap()
        pixmap.loadFromData(buf.getvalue(), "PNG")
        self.qr_label.setPixmap(pixmap)
        server_thread = threading.Thread(target=start_flask_server, args=(port,), daemon=True)
        server_thread.start()
        self.info_label.setText(f"Server running on port {port}.")
        self.open_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        self.restart_btn.setEnabled(True)
        self.server_running = True
    def stop_server(self):
        global flask_server, server_thread
        if not self.server_running:
            return
        try:
            if flask_server:
                flask_server.shutdown()
                flask_server = None
        except Exception as e:
            print("Error shutting down server:", e)
        if server_thread and server_thread.is_alive():
            server_thread.join(timeout=5)
        server_thread = None
        self.server_running = False
        self.info_label.setText("Server stopped.")
        self.open_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.restart_btn.setEnabled(False)
    def restart_server(self):
        self.stop_server()
        time.sleep(1)
        self.start_server()
    def open_in_browser(self):
        if self.url_label.text():
            url = QUrl(self.url_label.text())
            QDesktopServices.openUrl(url)

# ----------------- CURSES FALLBACK INTERFACE -----------------
def curses_interface():
    import curses
    def main_curses(stdscr):
        curses.echo()
        stdscr.clear()
        stdscr.addstr("VPS Explorer - Curses Interface\n")
        stdscr.addstr("Enter VPS IP: ")
        ip = stdscr.getstr().decode().strip()
        stdscr.addstr("Enter VPS Port (default 22): ")
        port_str = stdscr.getstr().decode().strip() or "22"
        stdscr.addstr("Enter Username (default root): ")
        user = stdscr.getstr().decode().strip() or "root"
        stdscr.addstr("Enter Password: ")
        curses.noecho()
        pw = stdscr.getstr().decode().strip()
        curses.echo()
        stdscr.addstr("\nConnecting...\n")
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(ip, int(port_str), user, pw, timeout=10)
            sftp = ssh.open_sftp()
        except Exception as e:
            stdscr.addstr("Connection failed: " + str(e) + "\n")
            stdscr.getch()
            return
        global global_ssh_client, global_sftp_client
        global_ssh_client = ssh
        global_sftp_client = sftp
        stdscr.addstr("Connected. Type 'exit' to quit terminal mode.\n")
        prompt = f"{user}@{ip}:~$ "
        while True:
            stdscr.addstr(prompt)
            cmd = stdscr.getstr().decode().strip()
            if cmd.lower() in ("exit", "quit"):
                break
            try:
                stdin, stdout, stderr = ssh.exec_command(cmd)
                output = stdout.read().decode() + stderr.read().decode()
            except Exception as e:
                output = "Error executing command: " + str(e)
            stdscr.addstr(output + "\n")
        ssh.close()
        sftp.close()
        stdscr.addstr("Disconnected. Press any key to exit.")
        stdscr.getch()
    import curses
    curses.wrapper(main_curses)

# ----------------- MAIN -----------------
def main():
    if not os.environ.get("DISPLAY") and sys.platform != "win32":
        print("No graphical UI detected. Launching curses interface...")
        curses_interface()
        sys.exit(0)
    app_qt = QApplication(sys.argv)
    login_dlg = LoginDialog()
    if login_dlg.exec() != QDialog.DialogCode.Accepted:
        sys.exit(0)
    ctrl = ControlDialog()
    ctrl.exec()
    sys.exit(0)

if __name__ == "__main__":
    main()
