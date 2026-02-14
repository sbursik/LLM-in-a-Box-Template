const themeSelect = document.getElementById("themeSelect");
const loginForm = document.getElementById("loginForm");
const loginSubmitBtn = loginForm.querySelector('button[type="submit"]');
const authPanel = document.getElementById("authPanel");
const eulaGate = document.getElementById("eulaGate");
const eulaContent = document.getElementById("eulaContent");
const eulaCheckbox = document.getElementById("eulaCheckbox");
const dashboardPanel = document.getElementById("dashboardPanel");
const chatPanel = document.getElementById("chatPanel");
const libraryPanel = document.getElementById("libraryPanel");
const openLibraryBtn = document.getElementById("openLibraryBtn");
const libraryList = document.getElementById("libraryList");
const libraryStatus = document.getElementById("libraryStatus");
const libraryTitle = document.getElementById("libraryTitle");
const libraryContent = document.getElementById("libraryContent");
const libraryTypeSelect = document.getElementById("libraryTypeSelect");
const libraryLocationLabel = document.getElementById("libraryLocationLabel");
const libraryHelpNote = document.getElementById("libraryHelpNote");
const uploadControls = document.getElementById("uploadControls");
const fileInput = document.getElementById("fileInput");
const uploadBtn = document.getElementById("uploadBtn");
const fileNameDisplay = document.getElementById("fileNameDisplay");
const storageInfo = document.getElementById("storageInfo");
const saveChatBtn = document.getElementById("saveChatBtn");
const newChatBtn = document.getElementById("newChatBtn");
const optionsBtn = document.getElementById("optionsBtn");
const optionsPanel = document.getElementById("optionsPanel");
const closeOptionsBtn = document.getElementById("closeOptionsBtn");
const viewEulaBtn = document.getElementById("viewEulaBtn");
const logoutBtn = document.getElementById("logoutBtn");
const resetPasswordBtn = document.getElementById("resetPasswordBtn");
const resetDefaultsBtn = document.getElementById("resetDefaultsBtn");
const chatForm = document.getElementById("chatForm");
const chatWindow = document.getElementById("chatWindow");
const modelGrid = document.getElementById("modelGrid");
const modelStatus = document.getElementById("modelStatus");
const refreshBtn = document.getElementById("refreshBtn");
const passwordPanel = document.getElementById("passwordPanel");
const passwordForm = document.getElementById("passwordForm");

const THEME_KEY = "llmBoxTheme";

const API_HEADERS = { "Content-Type": "application/json" };

// Track chat messages for saving
let chatHistory = [];
let eulaContentLoaded = false;

const setTheme = (theme) => {
  document.body.classList.toggle("theme-terminal", theme === "terminal");
  document.body.classList.toggle("theme-cmd", theme === "cmd");
  document.body.classList.toggle("theme-dark", theme === "dark");
  themeSelect.value = theme;
  localStorage.setItem(THEME_KEY, theme);
};

const setAuthenticated = (isAuthed, mustChangePassword = false) => {
  authPanel.hidden = isAuthed;
  passwordPanel.hidden = !isAuthed || !mustChangePassword;
  dashboardPanel.hidden = !isAuthed || mustChangePassword;
  chatPanel.hidden = !isAuthed || mustChangePassword;
  libraryPanel.hidden = !isAuthed || mustChangePassword;
  logoutBtn.disabled = !isAuthed;
  viewEulaBtn.hidden = !isAuthed;
  resetPasswordBtn.hidden = !isAuthed;
  resetDefaultsBtn.hidden = !isAuthed;
  if (!isAuthed) {
    optionsPanel.hidden = true;
  }
};

const loadEulaContent = async () => {
  if (eulaContentLoaded) {
    return;
  }
  try {
    const response = await fetch("/api/eula");
    const data = await response.json();
    if (response.ok && data.content) {
      eulaContent.textContent = data.content;
    } else {
      eulaContent.textContent = data.error || "EULA could not be loaded.";
    }
  } catch (error) {
    eulaContent.textContent = `EULA could not be loaded: ${error.message}`;
  }
  eulaContentLoaded = true;
};

const setEulaGateState = async (eulaAccepted) => {
  const requiresAcceptance = !eulaAccepted;
  eulaGate.hidden = !requiresAcceptance;
  eulaCheckbox.required = requiresAcceptance;

  if (requiresAcceptance) {
    await loadEulaContent();
    eulaCheckbox.checked = false;
    loginSubmitBtn.disabled = true;
    return;
  }

  eulaCheckbox.checked = true;
  loginSubmitBtn.disabled = false;
};

const loadSession = () => {
  const storedTheme = localStorage.getItem(THEME_KEY) || "dark";
  setTheme(storedTheme);
  fetchSession();
};

const appendChatMessage = (author, message) => {
  // Track message for saving (skip system messages)
  if (author !== "System") {
    chatHistory.push({ author, message });
  }
  
  const bubble = document.createElement("div");
  bubble.className = "chat-bubble";
  bubble.innerHTML = `<strong>${author}</strong><p>${message}</p>`;
  chatWindow.appendChild(bubble);
  chatWindow.scrollTop = chatWindow.scrollHeight;
};

const renderModels = (models) => {
  modelGrid.innerHTML = "";
  
  // Show count of loaded models at the top
  const loadedModels = models.filter(m => m.status === "loaded");
  if (loadedModels.length > 0) {
    const activeInfo = document.createElement("div");
    activeInfo.className = "model-active-info";
    activeInfo.innerHTML = `<strong>Active:</strong> ${loadedModels.map(m => m.name).join(", ")}`;
    modelGrid.appendChild(activeInfo);
  }
  
  models.forEach((model) => {
    const card = document.createElement("article");
    card.className = "model-card";

    const statusBadge = document.createElement("span");
    statusBadge.className = "badge";
    
    // Set badge text and styling based on status
    if (model.status === "loaded") {
      statusBadge.textContent = "✓ Loaded";
      statusBadge.style.backgroundColor = "#2ecc71";
    } else if (model.status === "loading") {
      statusBadge.textContent = "⏳ Loading...";
      statusBadge.style.backgroundColor = "#f39c12";
    } else if (model.status === "error") {
      statusBadge.textContent = "✗ Error";
      statusBadge.style.backgroundColor = "#e74c3c";
    } else {
      statusBadge.textContent = "Available";
      statusBadge.style.backgroundColor = "#95a5a6";
    }

    const actions = document.createElement("div");
    actions.className = "actions";

    const loadButton = document.createElement("button");
    loadButton.className = "primary keep-black";
    loadButton.textContent = "Load";
    loadButton.disabled = model.status === "loaded" || model.status === "loading";

    const unloadButton = document.createElement("button");
    unloadButton.className = "ghost";
    unloadButton.textContent = "Unload";
    unloadButton.disabled = model.status !== "loaded";

    loadButton.addEventListener("click", () => updateModel(model.id, "load"));
    unloadButton.addEventListener("click", () => updateModel(model.id, "unload"));

    actions.append(loadButton, unloadButton);

    card.innerHTML = `
      <div class="model-header">
        <h3>${model.name}</h3>
      </div>
      <p>${model.profile}</p>
    `;
    
    // Add error message if present
    if (model.status === "error" && model.error) {
      const errorMsg = document.createElement("p");
      errorMsg.className = "error-message";
      errorMsg.style.color = "#e74c3c";
      errorMsg.style.fontSize = "0.9em";
      errorMsg.style.marginTop = "0.5em";
      errorMsg.textContent = `Error: ${model.error}`;
      card.appendChild(errorMsg);
    }
    
    card.querySelector(".model-header").append(statusBadge);
    card.append(actions);
    modelGrid.append(card);
  });
};

const fetchSession = async () => {
  const response = await fetch("/api/session");
  const data = await response.json();
  await setEulaGateState(Boolean(data.eula_accepted));
  const mustChangePassword = Boolean(data.must_change_password);
  setAuthenticated(Boolean(data.authenticated), mustChangePassword);
  if (data.authenticated && !mustChangePassword) {
    await fetchModels();
  }
};

const fetchModels = async () => {
  modelStatus.textContent = "Loading model catalog...";
  const response = await fetch("/api/models");
  const data = await response.json();
  renderModels(data.models || []);
  modelStatus.textContent = "";
};

const updateModel = async (id, action) => {
  modelStatus.textContent = action === "load" ? "Loading model..." : "Unloading model...";
  
  const response = await fetch("/api/models", {
    method: "POST",
    headers: API_HEADERS,
    body: JSON.stringify({ id, action }),
  });
  const data = await response.json();
  renderModels(data.models || []);
  
  // If loading, poll for status updates
  if (action === "load") {
    const checkStatus = async () => {
      const statusResp = await fetch("/api/models");
      const statusData = await statusResp.json();
      const targetModel = statusData.models.find(m => m.id === id);
      
      renderModels(statusData.models || []);
      
      if (targetModel && targetModel.status === "loading") {
        // Still loading, check again
        setTimeout(checkStatus, 500);
      } else if (targetModel && targetModel.status === "loaded") {
        modelStatus.textContent = `✓ ${targetModel.name} ready for questions`;
        setTimeout(() => { modelStatus.textContent = ""; }, 3000);
      } else if (targetModel && targetModel.status === "error") {
        modelStatus.textContent = `✗ Failed to load ${targetModel.name}`;
        setTimeout(() => { modelStatus.textContent = ""; }, 5000);
      } else {
        modelStatus.textContent = "";
      }
    };
    
    // Start polling after a short delay
    setTimeout(checkStatus, 500);
  } else {
    modelStatus.textContent = "";
  }
};

const renderLibraryList = (files) => {
  libraryList.innerHTML = "";
  const libraryType = libraryTypeSelect.value;
  
  if (!files.length) {
    const empty = document.createElement("li");
    empty.className = "muted small";
    const typeName = libraryType === "chats" ? "saved chats" : 
                     libraryType === "personal" ? "personal files" : "guides";
    empty.textContent = `No ${typeName} found.`;
    libraryList.append(empty);
    return;
  }
  
  files.forEach((file) => {
    const item = document.createElement("li");
    
    // Check if file is clickable (default true for guides/chats, check flag for personal)
    const isClickable = file.clickable !== false;
    
    if (isClickable) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "library-link";
      button.textContent = file.name;
      button.addEventListener("click", () => loadLibraryFile(file.name));
      item.append(button);
    } else {
      // Non-clickable file - display as plain text
      const span = document.createElement("span");
      span.className = "library-file-name";
      span.textContent = file.name;
      item.append(span);
    }
    
    libraryList.append(item);
  });
};

const fetchLibraryList = async (type = "guides") => {
  const displayName = type === "chats" ? "chats" : 
                      type === "personal" ? "files" : "guides";
  libraryStatus.textContent = `Loading ${displayName}...`;
  const response = await fetch(`/api/library?type=${type}`);
  if (!response.ok) {
    libraryStatus.textContent = `Unable to load ${displayName}.`;
    return;
  }
  const data = await response.json();
  renderLibraryList(data.files || []);
  libraryStatus.textContent = "";
};

const loadLibraryFileToElement = async (name, titleElement, contentElement, type = "guides") => {
  titleElement.textContent = name;
  contentElement.textContent = "Loading...";
  const response = await fetch(`/api/library/file?name=${encodeURIComponent(name)}&type=${type}`);
  const data = await response.json();
  if (!response.ok) {
    contentElement.textContent = data.error || "Unable to load file.";
    return;
  }
  contentElement.textContent = data.content || "";
};

const loadLibraryFile = async (name) => {
  const type = libraryTypeSelect.value;
  loadLibraryFileToElement(name, libraryTitle, libraryContent, type);
};

let serverLogInterval = null;

const fetchServerLog = async () => {
  try {
    const response = await fetch("/api/library?type=server-log");
    const data = await response.json();
    if (data.log) {
      libraryContent.textContent = data.log;
      // Auto-scroll to bottom
      libraryContent.scrollTop = libraryContent.scrollHeight;
    }
  } catch (error) {
    libraryContent.textContent = `Error fetching log: ${error.message}`;
  }
};

const startServerLogRefresh = () => {
  // Clear any existing interval
  if (serverLogInterval) {
    clearInterval(serverLogInterval);
  }
  // Fetch immediately
  fetchServerLog();
  // Then refresh every 1 second
  serverLogInterval = setInterval(fetchServerLog, 1000);
};

const stopServerLogRefresh = () => {
  if (serverLogInterval) {
    clearInterval(serverLogInterval);
    serverLogInterval = null;
  }
};

const saveChatToFile = async () => {
  if (chatHistory.length === 0) {
    alert("No messages to save. Start a conversation first.");
    return;
  }
  
  saveChatBtn.disabled = true;
  saveChatBtn.textContent = "💾 Saving...";
  
  try {
    const response = await fetch("/api/chat/save", {
      method: "POST",
      headers: API_HEADERS,
      body: JSON.stringify({ messages: chatHistory }),
    });
    const data = await response.json();
    
    if (data.success) {
      alert(`Chat saved as: ${data.filename}`);
      // Clear chat history after successful save
      chatHistory = [];
    } else {
      alert(`Failed to save chat: ${data.error || "Unknown error"}`);
    }
  } catch (error) {
    alert(`Error saving chat: ${error.message}`);
  } finally {
    saveChatBtn.disabled = false;
    saveChatBtn.textContent = "💾 Save";
  }
};

const fetchStorageInfo = async () => {
  try {
    const response = await fetch("/api/storage/info");
    const data = await response.json();
    
    if (response.ok) {
      storageInfo.textContent = `Available space: ${data.free_display} of ${data.total_display}`;
    } else {
      storageInfo.textContent = "Unable to fetch storage info.";
    }
  } catch (error) {
    storageInfo.textContent = "Error loading storage info.";
  }
};

const handleFileUpload = async () => {
  const file = fileInput.files[0];
  if (!file) {
    alert("Please select a file to upload.");
    return;
  }
  
  uploadBtn.disabled = true;
  uploadBtn.textContent = "📤 Uploading...";
  
  try {
    const formData = new FormData();
    formData.append("file", file);
    
    const response = await fetch("/api/upload", {
      method: "POST",
      body: formData,
    });
    const data = await response.json();
    
    if (data.success) {
      alert(`File uploaded successfully: ${data.filename}`);
      fileInput.value = ""; // Clear the input
      fileNameDisplay.textContent = "No file chosen";
      uploadBtn.textContent = "📤 Upload";
      // Refresh the file list
      fetchLibraryList("personal");
      // Update storage info
      fetchStorageInfo();
    } else {
      alert(`Upload failed: ${data.error || "Unknown error"}`);
    }
  } catch (error) {
    alert(`Error uploading file: ${error.message}`);
  } finally {
    uploadBtn.disabled = false;
    uploadBtn.textContent = "📤 Upload";
  }
};

const updateLibraryUIForType = (type) => {
  // Update location label
  if (type === "guides") {
    libraryLocationLabel.innerHTML = '<strong>Guides location:</strong> <code>Survival Guides</code> folder on this drive';
    libraryLocationLabel.hidden = false;
    libraryHelpNote.hidden = false;
    uploadControls.hidden = true;
    libraryStatus.textContent = 'Select "View Folder" to load available guides.';
  } else if (type === "chats") {
    libraryLocationLabel.innerHTML = '<strong>Chats location:</strong> <code>Saved Chats</code> folder on this drive';
    libraryLocationLabel.hidden = false;
    libraryHelpNote.hidden = false;
    uploadControls.hidden = true;
    libraryStatus.textContent = 'Select "View Folder" to load saved chats.';
  } else if (type === "personal") {
    libraryLocationLabel.innerHTML = '<strong>Files location:</strong> <code>Personal Files</code> folder on this drive';
    libraryLocationLabel.hidden = false;
    libraryHelpNote.hidden = false;
    uploadControls.hidden = false;
    libraryStatus.textContent = 'Upload your personal files or select "View Folder" to view existing files. Only .txt files can be previewed.';
    fetchStorageInfo();
  } else if (type === "server-log") {
    libraryLocationLabel.hidden = true;
    libraryHelpNote.hidden = true;
    uploadControls.hidden = true;
    libraryStatus.textContent = 'Live server log (last 100 lines, auto-refreshing):';
  }
  
  // Clear current content
  libraryTitle.textContent = type === "server-log" ? "Server Log" : "Select a file to view";
  libraryContent.textContent = "";
};

themeSelect.addEventListener("change", (event) => {
  setTheme(event.target.value);
});

const toggleOptionsPanel = (forceOpen = null) => {
  if (forceOpen === true) {
    optionsPanel.hidden = false;
    return;
  }
  if (forceOpen === false) {
    optionsPanel.hidden = true;
    return;
  }
  optionsPanel.hidden = !optionsPanel.hidden;
};

const showEulaModal = async () => {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay active";

  const expandedPanel = document.createElement("div");
  expandedPanel.className = "panel-expanded";

  const header = document.createElement("div");
  header.className = "panel-header";
  header.innerHTML = `
    <h2>End User License Agreement</h2>
    <button class="ghost close-btn" title="Close">×</button>
  `;

  const content = document.createElement("pre");
  content.className = "eula-modal-content";
  content.textContent = "Loading EULA...";

  expandedPanel.appendChild(header);
  expandedPanel.appendChild(content);
  overlay.appendChild(expandedPanel);
  document.body.appendChild(overlay);

  const closeBtn = header.querySelector(".close-btn");
  const closeModal = () => {
    overlay.classList.remove("active");
    setTimeout(() => overlay.remove(), 200);
  };

  closeBtn.addEventListener("click", closeModal);
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) {
      closeModal();
    }
  });

  const handleEscape = (e) => {
    if (e.key === "Escape") {
      closeModal();
      document.removeEventListener("keydown", handleEscape);
    }
  };
  document.addEventListener("keydown", handleEscape);

  try {
    const response = await fetch("/api/eula");
    const data = await response.json();
    if (response.ok && data.content) {
      content.textContent = data.content;
    } else {
      content.textContent = data.error || "Unable to load EULA.";
    }
  } catch (error) {
    content.textContent = `Unable to load EULA: ${error.message}`;
  }
};

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  if (!eulaGate.hidden && !eulaCheckbox.checked) {
    alert("You must accept the EULA before signing in.");
    return;
  }

  const formData = new FormData(loginForm);
  const payload = Object.fromEntries(formData.entries());
  if (!eulaGate.hidden) {
    payload.accept_eula = eulaCheckbox.checked;
  }

  const response = await fetch("/api/login", {
    method: "POST",
    headers: API_HEADERS,
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok || !data.authenticated) {
    alert(data.error || "Login failed.");
    return;
  }

  await setEulaGateState(Boolean(data.eula_accepted));
  const mustChangePassword = Boolean(data.must_change_password);
  setAuthenticated(Boolean(data.authenticated), mustChangePassword);
  if (data.authenticated && !mustChangePassword) {
    await fetchModels();
  }
});

logoutBtn.addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST", headers: API_HEADERS });
  setAuthenticated(false);
});

resetPasswordBtn.addEventListener("click", async () => {
  const confirmed = confirm(
    "Reset your password to default? You will need to log in again with the default credentials."
  );
  if (!confirmed) return;

  resetPasswordBtn.disabled = true;
  const response = await fetch("/api/reset-password", {
    method: "POST",
    headers: API_HEADERS,
  });

  if (response.ok) {
    alert("Password reset. Please log in with default credentials.\n\nDefault: llminabox / myllm");
    setTimeout(() => {
      window.location.href = "/";
    }, 2000);
  } else {
    alert("Reset failed. Please try again.");
    resetPasswordBtn.disabled = false;
  }
});

resetDefaultsBtn.addEventListener("click", async () => {
  const confirmed = confirm(
    "⚠️ WARNING: This will reset the drive to its original state!\n\n" +
    "This action will:\n" +
    "• Reset your password to default\n" +
    "• Delete ALL saved chats\n" +
    "• Delete ALL personal files\n\n" +
    "This cannot be undone. Continue?"
  );
  if (!confirmed) return;

  const doubleCheck = confirm(
    "Are you absolutely sure? All your saved data will be permanently deleted."
  );
  if (!doubleCheck) return;

  resetDefaultsBtn.disabled = true;
  const response = await fetch("/api/reset-to-defaults", {
    method: "POST",
    headers: API_HEADERS,
  });

  if (response.ok) {
    alert("Drive reset to defaults. All saved data has been deleted.\n\nPlease refresh your browser.");
    setTimeout(() => {
      window.location.href = "/";
    }, 2000);
  } else {
    alert("Reset failed. Please try again.");
    resetDefaultsBtn.disabled = false;
  }
});

refreshBtn.addEventListener("click", fetchModels);

optionsBtn.addEventListener("click", () => toggleOptionsPanel());
closeOptionsBtn.addEventListener("click", () => toggleOptionsPanel(false));
viewEulaBtn.addEventListener("click", showEulaModal);

openLibraryBtn.addEventListener("click", () => {
  const type = libraryTypeSelect.value;
  if (type === "server-log") {
    startServerLogRefresh();
  } else {
    stopServerLogRefresh();
    fetchLibraryList(type);
  }
});

saveChatBtn.addEventListener("click", saveChatToFile);

newChatBtn.addEventListener("click", () => {
  if (chatHistory.length > 0) {
    const confirmed = confirm("Start a new chat? Current conversation will be cleared (save it first if needed).");
    if (!confirmed) return;
  }
  
  // Clear chat history
  chatHistory = [];
  
  // Clear chat window
  chatWindow.innerHTML = '';
  
  // Add welcome message
  const bubble = document.createElement("div");
  bubble.className = "chat-bubble assistant";
  bubble.innerHTML = '<strong>System</strong><p>New chat started. Ask your question.</p>';
  chatWindow.appendChild(bubble);
});

uploadBtn.addEventListener("click", () => {
  if (fileInput.files.length > 0) {
    // File already selected, trigger upload
    handleFileUpload();
  } else {
    // No file selected, open file picker
    fileInput.click();
  }
});

fileInput.addEventListener("change", (e) => {
  const file = fileInput.files[0];
  if (file) {
    fileNameDisplay.textContent = file.name;
    uploadBtn.textContent = "📤 Upload";
  } else {
    fileNameDisplay.textContent = "No file chosen";
    uploadBtn.textContent = "📤 Upload";
  }
});

libraryTypeSelect.addEventListener("change", () => {
  const type = libraryTypeSelect.value;
  updateLibraryUIForType(type);
  
  if (type === "server-log") {
    startServerLogRefresh();
  } else {
    stopServerLogRefresh();
    fetchLibraryList(type);
  }
});

passwordForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(passwordForm);
  const payload = Object.fromEntries(formData.entries());
  const response = await fetch("/api/password", {
    method: "POST",
    headers: API_HEADERS,
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (data.success) {
    passwordForm.reset();
    setAuthenticated(true, false);
    await fetchModels();
  }
});

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = chatForm.elements.message;
  if (!input.value.trim()) {
    return;
  }
  appendChatMessage("You", input.value.trim());
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: API_HEADERS,
    body: JSON.stringify({ message: input.value.trim() }),
  });
  const data = await response.json();
  
  // Use the model name returned by the API
  const modelName = data.model_name || "Assistant";
  appendChatMessage(modelName, data.reply || "No response available.");
  input.value = "";
});

// Fullscreen panel expansion
const expandChatBtn = document.getElementById("expandChatBtn");
const expandLibraryBtn = document.getElementById("expandLibraryBtn");

function createModalOverlay(panelType, panelTitle) {
  // Create modal overlay
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay active";
  
  // Create expanded panel container
  const expandedPanel = document.createElement("div");
  expandedPanel.className = "panel-expanded";
  
  // Create header with close button
  const header = document.createElement("div");
  header.className = "panel-header";
  header.innerHTML = `
    <h2>${panelTitle}</h2>
    <button class="ghost close-btn" title="Close">×</button>
  `;
  expandedPanel.appendChild(header);
  
  // Close handler
  const closeBtn = header.querySelector(".close-btn");
  const closeModal = () => {
    overlay.classList.remove("active");
    setTimeout(() => overlay.remove(), 200);
  };
  
  closeBtn.addEventListener("click", closeModal);
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) closeModal();
  });
  
  // Handle Escape key
  const handleEscape = (e) => {
    if (e.key === "Escape") {
      closeModal();
      document.removeEventListener("keydown", handleEscape);
    }
  };
  document.addEventListener("keydown", handleEscape);
  
  // Build content based on panel type
  if (panelType === "chat") {
    // Create chat window
    const chatWindowExpanded = document.createElement("div");
    chatWindowExpanded.className = "chat-window";
    
    // Copy existing messages
    const existingMessages = chatWindow.querySelectorAll(".chat-bubble");
    if (existingMessages.length > 0) {
      existingMessages.forEach(msg => {
        chatWindowExpanded.appendChild(msg.cloneNode(true));
      });
    } else {
      // Add welcome message if no messages exist
      const welcomeBubble = document.createElement("div");
      welcomeBubble.className = "chat-bubble assistant";
      welcomeBubble.innerHTML = `<strong>System</strong><p>Welcome back. Select a model, then ask a question.</p>`;
      chatWindowExpanded.appendChild(welcomeBubble);
    }
    
    // Create chat form
    const chatFormExpanded = document.createElement("form");
    chatFormExpanded.className = "chat-input";
    chatFormExpanded.innerHTML = `
      <input
        type="text"
        name="message"
        placeholder="Ask about water purification, shelter, or resource planning..."
        required
      />
      <button type="submit" class="primary keep-black">Send</button>
    `;
    
    // Add form handler
    chatFormExpanded.addEventListener("submit", async (event) => {
      event.preventDefault();
      const input = chatFormExpanded.elements.message;
      if (!input.value.trim()) return;
      
      const userMessage = input.value.trim();
      
      // Add to expanded window
      appendMessageToWindow(chatWindowExpanded, "You", userMessage);
      
      // Send request
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: API_HEADERS,
        body: JSON.stringify({ message: userMessage }),
      });
      const data = await response.json();
      
      if (data.error) {
        appendMessageToWindow(chatWindowExpanded, "System", `Error: ${data.error}`);
        return;
      }
      
      const modelName = data.model_name || "Assistant";
      
      // Add to expanded window
      appendMessageToWindow(chatWindowExpanded, modelName, data.reply || "No response available.");
      
      // Also update the main chat window
      appendChatMessage("You", userMessage);
      appendChatMessage(modelName, data.reply || "No response available.");
      
      input.value = "";
    });
    
    expandedPanel.appendChild(chatWindowExpanded);
    expandedPanel.appendChild(chatFormExpanded);
    
  } else if (panelType === "library") {
    // Clone library content
    const libraryContentCloned = libraryPanel.querySelector(".library-body").cloneNode(true);
    
    // Get current library type
    const currentLibraryType = libraryTypeSelect.value;
    
    // Re-attach event listeners to library buttons using event delegation
    libraryContentCloned.addEventListener("click", (e) => {
      if (e.target.classList.contains("library-link")) {
        const fileName = e.target.textContent;
        // Load file into the modal's library reader
        const modalTitle = libraryContentCloned.querySelector("#libraryTitle");
        const modalContent = libraryContentCloned.querySelector("#libraryContent");
        loadLibraryFileToElement(fileName, modalTitle, modalContent, currentLibraryType);
      }
    });
    
    expandedPanel.appendChild(libraryContentCloned);
  }
  
  overlay.appendChild(expandedPanel);
  document.body.appendChild(overlay);
  
  return overlay;
}

function appendMessageToWindow(windowElement, author, message) {
  const bubble = document.createElement("div");
  bubble.className = "chat-bubble";
  bubble.innerHTML = `<strong>${author}</strong><p>${message}</p>`;
  windowElement.appendChild(bubble);
  windowElement.scrollTop = windowElement.scrollHeight;
}

expandChatBtn.addEventListener("click", () => {
  createModalOverlay("chat", "Chat Console");
});

expandLibraryBtn.addEventListener("click", () => {
  createModalOverlay("library", "Offline Survival Library");
});

eulaCheckbox.addEventListener("change", () => {
  if (!eulaGate.hidden) {
    loginSubmitBtn.disabled = !eulaCheckbox.checked;
  }
});

loadSession();

