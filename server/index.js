const express = require("express");
const cors = require("cors");
const bodyParser = require("body-parser");
const path = require("path");
const axios = require("axios");

const app = express();
const PORT = process.env.PORT || 3000;
const PYTHON_API_URL = "http://localhost:5000/api";

// Middleware
app.use(cors());
app.use(bodyParser.json());
app.use(bodyParser.urlencoded({ extended: true }));

// Serve static files from the frontend build directory in production
if (process.env.NODE_ENV === "production") {
  app.use(express.static(path.join(__dirname, "../frontend/dist")));
}

// Root route handler
app.get("/", (req, res) => {
  res.send("Server is running. API endpoints are available at /api/*");
});

// Health check endpoint
app.get("/api/health", async (req, res) => {
  try {
    // Check if Python backend is running
    const response = await axios.get(`${PYTHON_API_URL}/health`);
    res.json({ status: "ok", backend: response.data });
  } catch (error) {
    console.error("Error checking backend health:", error);
    res.status(500).json({
      status: "error",
      message: "Backend health check failed",
      error: error.message,
    });
  }
});

// API routes
app.post("/api/chat", async (req, res) => {
  try {
    console.log("Received chat request:", req.body);

    // Ensure message is a string
    const message = String(req.body.message || "");
    const session_id = String(req.body.session_id || "default");

    const response = await axios.post(`${PYTHON_API_URL}/chat`, {
      message,
      session_id,
    });

    console.log("Python backend response:", response.data);
    res.json(response.data);
  } catch (error) {
    console.error("Error forwarding to Python backend:", error);
    console.error("Error details:", error.response?.data || error.message);

    res.status(500).json({
      error: "Failed to process request",
      details: error.response?.data || error.message,
    });
  }
});

app.post("/api/chat/reset", async (req, res) => {
  try {
    console.log("Received reset request:", req.body);

    // Ensure session_id is a string
    const session_id = String(req.body.session_id || "default");

    const response = await axios.post(`${PYTHON_API_URL}/chat/reset`, {
      session_id,
    });

    res.json(response.data);
  } catch (error) {
    console.error("Error forwarding to Python backend:", error);
    res.status(500).json({
      error: "Failed to reset chat",
      details: error.message,
    });
  }
});

app.post("/api/refresh-data", async (req, res) => {
  try {
    console.log("Received refresh-data request");
    const response = await axios.post(`${PYTHON_API_URL}/refresh-data`);
    res.json(response.data);
  } catch (error) {
    console.error("Error forwarding to Python backend:", error);
    res.status(500).json({
      error: "Failed to refresh data",
      details: error.message,
    });
  }
});

// Endpoint for downloading quotations
app.get("/api/quotations/download", async (req, res) => {
  try {
    const sessionId = req.query.session_id;
    if (!sessionId) {
      return res.status(400).json({ error: "No session ID provided" });
    }

    console.log(`Downloading quotations for session: ${sessionId}`);

    // Forward the request to the Python backend
    const response = await axios.get(`${PYTHON_API_URL}/quotations/download`, {
      params: { session_id: sessionId },
      responseType: "arraybuffer", // Important for binary data
    });

    // Set headers for file download
    res.setHeader("Content-Type", "application/pdf");
    res.setHeader(
      "Content-Disposition",
      `attachment; filename=quotations_${sessionId}.pdf`
    );

    // Send the file data
    return res.send(Buffer.from(response.data));
  } catch (error) {
    console.error("Error downloading quotations:", error);
    return res.status(500).json({
      error: "Failed to download quotations",
      details: error.message,
    });
  }
});

// Serve the Vue app for any other routes in production
if (process.env.NODE_ENV === "production") {
  app.get("*", (req, res) => {
    res.sendFile(path.join(__dirname, "../frontend/dist/index.html"));
  });
}

// Error handling middleware
app.use((err, req, res, next) => {
  console.error(err.stack);
  res.status(500).json({
    error: "Something went wrong on the server",
    message: process.env.NODE_ENV === "development" ? err.message : undefined,
  });
});

// Start server
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
  console.log(`Access the application at http://localhost:${PORT}`);
});
