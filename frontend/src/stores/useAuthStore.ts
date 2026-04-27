import { create } from "zustand";
import {
  login,
  refreshSession,
  getApmIdFromToken,
  type AuthTokens,
} from "../api/auth";
import { clearCredentialsCache } from "../api/credentials";

const STORAGE_KEY = "pharmassist_auth";

interface AuthState {
  tokens: AuthTokens | null;
  apmId: string;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;

  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
  getIdToken: () => string | null;
}

function loadPersistedTokens(): { tokens: AuthTokens; apmId: string } | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const tokens = JSON.parse(raw) as AuthTokens;
    if (!tokens.idToken || !tokens.refreshToken) return null;
    const apmId = getApmIdFromToken(tokens.idToken);
    return { tokens, apmId };
  } catch {
    localStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

function persistTokens(tokens: AuthTokens | null) {
  if (tokens) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(tokens));
  } else {
    localStorage.removeItem(STORAGE_KEY);
  }
}

const persisted = loadPersistedTokens();

const useAuthStore = create<AuthState>((set, get) => ({
  tokens: persisted?.tokens ?? null,
  apmId: persisted?.apmId ?? "",
  isAuthenticated: !!persisted,
  isLoading: false,
  error: null,

  login: async (email, password) => {
    set({ isLoading: true, error: null });
    try {
      const tokens = await login(email, password);
      const apmId = getApmIdFromToken(tokens.idToken);
      persistTokens(tokens);
      set({ tokens, apmId, isAuthenticated: true });
    } catch {
      set({ error: "Credenciales inválidas. Verificá tu email y contraseña." });
    } finally {
      set({ isLoading: false });
    }
  },

  logout: () => {
    clearCredentialsCache();
    persistTokens(null);
    set({ tokens: null, apmId: "", isAuthenticated: false });
  },

  refresh: async () => {
    const { tokens } = get();
    if (!tokens?.refreshToken) return;
    try {
      const newTokens = await refreshSession(tokens.refreshToken);
      const apmId = getApmIdFromToken(newTokens.idToken);
      persistTokens(newTokens);
      set({ tokens: newTokens, apmId });
    } catch {
      persistTokens(null);
      set({ tokens: null, apmId: "", isAuthenticated: false });
    }
  },

  getIdToken: () => get().tokens?.idToken ?? null,
}));

// On load, if we have persisted tokens, try to refresh them silently
if (persisted) {
  useAuthStore.getState().refresh();
}

export default useAuthStore;
