import { createStore } from "vuex";
import chatModule from "./modules/chat";

export default createStore({
  state: {},
  getters: {},
  mutations: {},
  actions: {},
  modules: {
    chat: chatModule,
  },
});
