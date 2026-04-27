import { createTheme } from '@mui/material/styles';
import { esES } from '@mui/material/locale';

export function buildTheme(mode: 'light' | 'dark') {
  const isDark = mode === 'dark';

  return createTheme(
    {
      palette: {
        mode,
        primary: {
          main: isDark ? '#5C9CE6' : '#1565C0',
          dark: '#0D47A1',
          light: '#64B5F6',
        },
        secondary: {
          main: isDark ? '#CE93D8' : '#8E24AA',
          dark: '#6A1B9A',
          light: '#BA68C8',
        },
        error: { main: '#E91E63', light: '#FF5252' },
        background: {
          default: isDark ? '#0F1318' : '#F0F2F5',
          paper: isDark ? '#1A1F27' : '#FFFFFF',
        },
      },
      typography: {
        fontFamily: '"Inter", "Roboto", "Helvetica", "Arial", sans-serif',
      },
      components: {
        MuiAppBar: {
          styleOverrides: {
            root: {
              background: isDark
                ? 'linear-gradient(135deg, #0D1B2A 0%, #1B2838 50%, #1A1F35 100%)'
                : 'linear-gradient(135deg, #0D47A1 0%, #1565C0 40%, #1E88E5 100%)',
              boxShadow: isDark
                ? '0 1px 8px rgba(0,0,0,0.4)'
                : '0 2px 12px rgba(13,71,161,0.3)',
            },
          },
        },
        MuiCard: {
          defaultProps: { elevation: 0 },
          styleOverrides: {
            root: {
              borderRadius: 14,
              border: `1px solid ${isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.08)'}`,
              backdropFilter: 'blur(8px)',
            },
          },
        },
        MuiFab: {
          defaultProps: { color: 'primary' },
        },
        MuiChip: {
          styleOverrides: {
            root: { borderRadius: 8 },
          },
        },
      },
    },
    esES,
  );
}

// Default export for backward compat
const theme = buildTheme('light');
export default theme;
