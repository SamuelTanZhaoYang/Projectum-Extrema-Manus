<template>
  <div class="app">
    <header class="app-header">
      <h1>Service Quotation Assistant</h1>
    </header>
    <main class="split-layout">
      <router-view />
    </main>
    <footer>
      <p>© {{ new Date().getFullYear() }} Service Quotation System</p>
    </footer>
  </div>
</template>

<script>
export default {
  name: "App",
};
</script>

<style>
.app {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}

.app-header {
  background-color: #2c3e50;
  color: white;
  padding: 15px 20px;
  text-align: center;
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
}

.app-header h1 {
  margin: 0;
  font-size: 24px;
}

main.split-layout {
  display: flex;
  flex: 1;
  overflow: hidden;
}

footer {
  padding: 10px;
  text-align: center;
  background-color: #f5f5f5;
  border-top: 1px solid #ddd;
  font-size: 14px;
  color: #666;
}

@media (max-width: 768px) {
  main.split-layout {
    flex-direction: column;
  }
}
</style>
