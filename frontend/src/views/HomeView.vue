<template>
  <div class="home">
    <div class="chat-panel">
      <ChatInterface />
    </div>
    <div class="quotation-panel">
      <QuotationCanvas />
    </div>
  </div>
</template>

<script>
import ChatInterface from "@/components/ChatInterface.vue";
import QuotationCanvas from "@/components/QuotationCanvas.vue";

export default {
  name: "HomeView",
  components: {
    ChatInterface,
    QuotationCanvas,
  },
};
</script>

<style scoped>
.home {
  display: flex;
  width: 100%;
  height: 100%;
}

.chat-panel {
  flex: 1;
  border-right: 1px solid #ddd;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.quotation-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background-color: #f9f9f9;
}

@media (max-width: 768px) {
  .home {
    flex-direction: column;
  }

  .chat-panel,
  .quotation-panel {
    flex: none;
    height: 50%;
    border-right: none;
  }

  .chat-panel {
    border-bottom: 1px solid #ddd;
  }
}
</style>
