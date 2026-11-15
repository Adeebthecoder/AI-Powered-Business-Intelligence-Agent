// AppContext.jsx
// Shared state that many pages need:
//   - who is logged in
//   - the list of datasets and which one is selected
//   - the chat messages of the Ask page (kept here so they survive page changes)

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, getToken, setToken, setUnauthorizedHandler } from "./api.js";

const AppContext = createContext(null);
const DATASET_KEY = "bi_agent_dataset";

export function AppProvider({ children }) {
  const [user, setUser] = useState(null);
  const [checkingLogin, setCheckingLogin] = useState(true);
  const [datasets, setDatasets] = useState([]);
  const [datasetId, setDatasetIdState] = useState(
    Number(localStorage.getItem(DATASET_KEY)) || null
  );
  const [chats, setChats] = useState({}); // { datasetId: [messages] }
  const [health, setHealth] = useState(null); // LLM mode, shown in the top bar

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    setDatasets([]);
    setChats({});
  }, []);

  const setDatasetId = useCallback((id) => {
    setDatasetIdState(id);
    if (id) localStorage.setItem(DATASET_KEY, String(id));
    else localStorage.removeItem(DATASET_KEY);
  }, []);

  const refreshDatasets = useCallback(async () => {
    const list = await api("/api/datasets");
    setDatasets(list);
    // Keep the selection valid: fall back to the newest dataset.
    setDatasetIdState((current) => {
      if (list.some((d) => d.dataset_id === current)) return current;
      const next = list.length ? list[0].dataset_id : null;
      if (next) localStorage.setItem(DATASET_KEY, String(next));
      return next;
    });
    return list;
  }, []);

  const login = useCallback(
    async (tokenReply) => {
      setToken(tokenReply.access_token);
      setUser(tokenReply.user);
      await refreshDatasets();
    },
    [refreshDatasets]
  );

  // On page load: if a token is saved, check that it still works.
  useEffect(() => {
    setUnauthorizedHandler(logout);
    api("/api/health").then(setHealth).catch(() => setHealth(null));
    if (!getToken()) {
      setCheckingLogin(false);
      return;
    }
    api("/api/auth/me")
      .then(async (me) => {
        setUser(me);
        await refreshDatasets();
      })
      .catch(() => logout())
      .finally(() => setCheckingLogin(false));
  }, [logout, refreshDatasets]);

  const addChatMessage = useCallback((id, message) => {
    setChats((all) => ({ ...all, [id]: [...(all[id] || []), message] }));
  }, []);

  const clearChat = useCallback((id) => {
    setChats((all) => ({ ...all, [id]: [] }));
  }, []);

  const value = useMemo(
    () => ({
      user, checkingLogin, login, logout, health,
      datasets, refreshDatasets, datasetId, setDatasetId,
      currentDataset: datasets.find((d) => d.dataset_id === datasetId) || null,
      chats, addChatMessage, clearChat,
    }),
    [user, checkingLogin, login, logout, health, datasets, refreshDatasets, datasetId,
     setDatasetId, chats, addChatMessage, clearChat]
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  return useContext(AppContext);
}
