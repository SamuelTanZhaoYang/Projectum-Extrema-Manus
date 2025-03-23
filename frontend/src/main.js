import { createApp } from "vue";
import App from "./App.vue";
import router from "./router";
import store from "./store";

// Just import the plugin to make it available globally
import "jspdf-autotable";

// Create the app and use router and store
const app = createApp(App);
app.use(router);
app.use(store);
app.mount("#app");
