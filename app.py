#!/usr/bin/env python3
"""
Single-file PyQt6 + Flask + Paramiko Explorer with Draggable Splitters,
Custom Scrollbars, and Plain Terminal Output

Features:
- PyQt login dialog (or curses fallback) with default port "22" and username "root"
- Control dialog with improved process management
- Web interface with two tabs:
    • Explorer: Scrollable directory tree and Code Editor separated by a draggable vertical splitter.
    • Terminal: A realistic terminal emulator with a draggable horizontal splitter between output and input.
- Custom CSS styles for scrollbars.
- Terminal output is rendered as plain text (ANSI codes will not be converted).
"""

import sys, os, stat, time, threading, random, socket, io, re, tempfile
import paramiko
from flask import Flask, request, jsonify, send_file, render_template_string
from werkzeug.serving import make_server

# ----------------- GLOBALS -----------------
global_ssh_client = None
global_sftp_client = None
flask_server = None
server_thread = None

app = Flask(__name__)

# ----------------- HTML TEMPLATE -----------------
# Note the new <div> elements with ids "splitter-explorer" and "splitter-terminal"
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
      background-color: #000;
      color: #0ff;
      font-family: monospace;
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
      text-wrap-mode: nowrap;
      color: wheat;
    }
    .tree-view li::before {
      content: '';
      position: absolute;
      top: 5px;
      left: -6px;
      width: 21px;
      border-bottom: 1px solid grey;
      border-bottom-left-radius: 3rem;
      padding: 5px;
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
    /* Terminal container: added horizontal splitter */
    #terminal-container {
      display: none;
      flex-direction: column;
      background-color: #000;
      padding: 10px;
      box-sizing: border-box;
      overflow: hidden;
    }
    #terminal-output {
      overflow-y: auto;
      background-color: #000;
      border: 1px solid #0ff;
      padding: 10px;
      font-family: monospace;
      white-space: pre-wrap;
    }
    /* Draggable horizontal splitter */
    #splitter-terminal {
      height: 5px;
      cursor: row-resize;
      background-color: #0ff;
    }
    #terminal-input {
      width: 100%;
      background-color: #000;
      border: 1px solid #0ff;
      color: #0ff;
      padding: 5px;
      font-family: monospace;
      box-sizing: border-box;
    }
  </style>
</head>
<body>
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
        </div>
        <div class="editor-content">
          <textarea id="codeEditor"></textarea>
        </div>
      </div>
    </div>
    <!-- Terminal Container with adjustable splitter -->
    <div id="terminal-container" class="d-flex">
      <div id="terminal-output"></div>
      <div id="splitter-terminal"></div>
      <input type="text" id="terminal-input" placeholder="Type your command and hit Enter...">
    </div>
  </div>

  <!-- CREATE ITEM MODAL -->
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
  // Terminal prompt string (simulate (venv) if needed)
  let terminalPrompt = "vps@remote:~$ ";

  document.addEventListener("DOMContentLoaded", function(){
    // Initialize CodeMirror editor for Explorer
    editor = CodeMirror.fromTextArea(document.getElementById("codeEditor"), {
      lineNumbers: true,
      mode: "markdown",
      theme: "rubyblue",
      indentWithTabs: true,
      indentUnit: 4,
      tabSize: 4,
      highlightSelectionMatches: true,
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
      let target = prompt("Enter target directory for upload:", currentSelectedPath);
      if(target === null) return;
      document.getElementById("uploadInput").dataset.targetPath = target;
      document.getElementById("uploadInput").click();
    });
    document.getElementById("uploadInput").addEventListener("change", uploadFiles);
    document.getElementById("deletePathBtn").addEventListener("click", deletePath);
    document.getElementById("downloadBtn").addEventListener("click", function(e){
      if(!currentSelectedPath){
        e.preventDefault();
        alert("Select a file/folder to download.");
      } else {
        let target = prompt("Enter target path for download (or leave blank for current):", currentSelectedPath);
        if(target === null) { e.preventDefault(); return; }
        if(target.trim() === "") target = currentSelectedPath;
        this.href = "/download/?path=" + encodeURIComponent(target);
      }
    });

    // Tab switching for Explorer/Terminal
    document.getElementById("tab-explorer").addEventListener("click", function(e){
      e.preventDefault();
      document.getElementById("explorer-container").style.display = "flex";
      document.getElementById("terminal-container").style.display = "none";
      document.querySelector("#tab-explorer").classList.add("active");
      document.querySelector("#tab-terminal").classList.remove("active");
    });
    document.getElementById("tab-terminal").addEventListener("click", function(e){
      e.preventDefault();
      document.getElementById("explorer-container").style.display = "none";
      document.getElementById("terminal-container").style.display = "flex";
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
        executeTerminalCommand(cmd);
        this.value = "";
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

    // Set up splitter for Terminal (horizontal)
    const splitterTerminal = document.getElementById("splitter-terminal");
    const terminalOutput = document.getElementById("terminal-output");
    splitterTerminal.addEventListener("mousedown", function(e) {
      e.preventDefault();
      document.addEventListener("mousemove", onDragTerminal);
      document.addEventListener("mouseup", stopDragTerminal);
    });
    function onDragTerminal(e) {
      const containerRect = document.getElementById("terminal-container").getBoundingClientRect();
      let newOutputHeight = e.clientY - containerRect.top;
      if(newOutputHeight < 50) newOutputHeight = 50;
      if(newOutputHeight > containerRect.height - 30) newOutputHeight = containerRect.height - 30;
      terminalOutput.style.height = newOutputHeight + "px";
    }
    function stopDragTerminal(e) {
      document.removeEventListener("mousemove", onDragTerminal);
      document.removeEventListener("mouseup", stopDragTerminal);
    }
  });

  // Append text to terminal output with auto-scroll
  function appendToTerminal(text) {
    let termOut = document.getElementById("terminal-output");
    termOut.innerHTML += text;
    termOut.scrollTop = termOut.scrollHeight;
  }

  // Execute terminal command via AJAX
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
    }
    return { mode, fileType };
  }

  // Load file content and update CodeMirror
  async function loadFileContents(path) {
    let url = "/ajax/file/?path=" + encodeURIComponent(path);
    let res = await fetch(url);
    let data = await res.json();
    if(data.status === 'ok'){
      editor.setValue(data.content);
      let { mode, fileType } = detectModeFromExtension(path);
      editor.setOption("mode", mode);
      document.getElementById("fileTypeTag").textContent = fileType;
    } else {
      alert(data.message || "Error loading file.");
    }
  }

  // Build directory tree recursively
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

  // Toggle directory expansion
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

  // Save file
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

  // Delete path (file or folder)
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
          editor.setValue("");
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

  // Modal for creating files/folders
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

  // Create item (file/folder)
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

  // Upload multiple files
  function uploadFiles(){
    let files = this.files;
    if(!files || files.length===0) return;
    let target = this.dataset.targetPath || currentSelectedPath;
    if(!isDirPath(target)) target = parentDir(target);
    let fd = new FormData();
    fd.append("parent_path", target);
    for(let i=0; i<files.length; i++){
      fd.append("file_"+i, files[i]);
    }
    fetch("/ajax/upload/", { method:"POST", body: fd })
    .then(r=>r.json())
    .then(data=>{
      if(data.status === 'ok'){
        alert(data.message + "\nUploaded to: " + target);
        buildDirectoryTree(basePath, document.getElementById("directoryTree"));
      } else {
        alert("Error: " + data.message);
      }
    })
    .catch(err=>{
      alert("Failed to upload: " + err);
    });
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
    upload_count = 0
    for key in request.files.keys():
        f = request.files[key]
        if f:
            temp_path = tempfile.mktemp()
            f.save(temp_path)
            remote_path = sanitize_path(os.path.join(parent_path, f.filename))
            try:
                global_sftp_client.put(temp_path, remote_path)
                upload_count += 1
            except Exception as e:
                return jsonify(status="error", message=str(e))
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
    return jsonify(status="ok", message=f"Uploaded {upload_count} file(s)")

@app.route("/download/", methods=["GET"])
def download_file():
    if not global_sftp_client:
        return "SFTP not connected!", 500
    path = request.args.get("path", "")
    if not path:
        return "No path provided", 400
    try:
        st = global_sftp_client.stat(path)
        # Check if the path is a directory
        if stat.S_ISDIR(st.st_mode):
            import zipfile
            # Create a temporary ZIP file
            tmp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
            tmp_zip.close()
            
            # Recursive function to add remote directory contents to the ZIP file
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
                # Use the basename of the directory as the root folder in the ZIP archive.
                add_dir_to_zip(global_sftp_client, path, os.path.basename(path))
            
            return send_file(tmp_zip.name, as_attachment=True, download_name=os.path.basename(path) + ".zip")
        else:
            # If it's a file, download it directly.
            tmpf = tempfile.NamedTemporaryFile(delete=False)
            global_sftp_client.get(path, tmpf.name)
            tmpf.close()
            return send_file(tmpf.name, as_attachment=True, download_name=os.path.basename(path))
    except Exception as e:
        return str(e), 500


# New route: Terminal command execution
@app.route("/terminal/execute/", methods=["POST"])
def terminal_execute():
    if not global_ssh_client:
        return jsonify(status="error", message="SSH not connected!")
    cmd = request.form.get("command", "")
    if not cmd:
        return jsonify(status="error", message="No command provided")
    try:
        stdin, stdout, stderr = global_ssh_client.exec_command(cmd)
        output = stdout.read().decode("utf-8") + stderr.read().decode("utf-8")
        return jsonify(status="ok", output=output)
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
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
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
        self.port_edit.setText("22")  # Default port
        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText("Username")
        self.user_edit.setText("root")  # Default username
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
            url = self.url_label.text()
            if os.name == 'nt':
                os.system(f'start {url}')
            elif sys.platform.startswith('darwin'):
                os.system(f'open {url}')
            else:
                os.system(f'xdg-open {url}')

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
