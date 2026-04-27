import { create } from 'zustand';

type ThemeMode = 'light' | 'dark';

interface ThemeState {
  mode: ThemeMode;
  toggleMode: () => void;
}

const useThemeStore = create<ThemeState>((set) => ({
  mode: (localStorage.getItem('theme-mode') as ThemeMode) || 'light',
  toggleMode: () =>
    set((s) => {
      const next = s.mode === 'light' ? 'dark' : 'light';
      localStorage.setItem('theme-mode', next);
      return { mode: next };
    }),
}));

export default useThemeStore;
