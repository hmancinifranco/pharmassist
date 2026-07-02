import { createTheme } from '@mui/material/styles';
import { esES } from '@mui/material/locale';
import type {} from '@mui/x-data-grid/themeAugmentation';

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
        // Dark mode text overrides — WCAG AA compliant (≥4.5:1 contrast vs paper #1A1F27)
        ...(isDark && {
          text: {
            primary: '#e0e0e0',   // ~10.2:1 contrast vs paper
            secondary: '#a0a0a0', // ~5.5:1 contrast vs paper
          },
        }),
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
              backdropFilter: 'blur(8px)',
              ...(isDark
                ? {
                    backgroundColor: '#1A1F27',
                    border: '1px solid rgba(255,255,255,0.12)',
                  }
                : {
                    border: '1px solid rgba(0,0,0,0.08)',
                  }),
            },
          },
        },
        MuiFab: {
          defaultProps: { color: 'primary' },
        },
        MuiChip: {
          styleOverrides: {
            root: {
              borderRadius: 8,
              ...(isDark && {
                backgroundColor: 'rgba(144, 202, 249, 0.16)',
                border: '1px solid rgba(144, 202, 249, 0.5)',
                color: '#90caf9', // ~5.2:1 contrast vs chip bg on dark paper
              }),
            },
          },
        },
        MuiSkeleton: {
          styleOverrides: {
            root: {
              ...(isDark && {
                backgroundColor: 'rgba(255,255,255,0.08)',
              }),
            },
          },
        },
        MuiDataGrid: {
          styleOverrides: {
            root: {
              ...(isDark && {
                borderColor: 'rgba(255,255,255,0.12)',
                '& .MuiDataGrid-cell': {
                  borderColor: 'rgba(255,255,255,0.08)',
                },
                '& .MuiDataGrid-columnHeaders': {
                  backgroundColor: '#2d2d2d',
                },
              }),
            },
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
