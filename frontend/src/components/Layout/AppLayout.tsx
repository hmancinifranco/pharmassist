import { type ReactNode } from 'react';
import AppBar from '@mui/material/AppBar';
import Box from '@mui/material/Box';
import IconButton from '@mui/material/IconButton';
import Toolbar from '@mui/material/Toolbar';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import DarkModeIcon from '@mui/icons-material/DarkMode';
import LightModeIcon from '@mui/icons-material/LightMode';
import LocalPharmacyIcon from '@mui/icons-material/LocalPharmacy';
import LogoutIcon from '@mui/icons-material/Logout';
import useAuthStore from '../../stores/useAuthStore';
import useThemeStore from '../../stores/useThemeStore';

interface AppLayoutProps {
  children: ReactNode;
}

export default function AppLayout({ children }: AppLayoutProps) {
  const apmId = useAuthStore((s) => s.apmId);
  const logout = useAuthStore((s) => s.logout);
  const mode = useThemeStore((s) => s.mode);
  const toggleMode = useThemeStore((s) => s.toggleMode);

  // Show first name only
  const displayName = apmId ? apmId.split(' ')[0] : '';

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <AppBar position="sticky" elevation={1}>
        <Toolbar>
          <LocalPharmacyIcon sx={{ mr: 1 }} />
          <Typography variant="h6" component="h1" noWrap sx={{ flexGrow: 1 }}>
            PharmAssist
          </Typography>

          {displayName && (
            <Typography variant="body2" sx={{ mr: 1, opacity: 0.9 }}>
              {displayName}
            </Typography>
          )}

          <Tooltip title={mode === 'light' ? 'Modo oscuro' : 'Modo claro'}>
            <IconButton color="inherit" onClick={toggleMode} size="small">
              {mode === 'light' ? <DarkModeIcon /> : <LightModeIcon />}
            </IconButton>
          </Tooltip>

          {apmId && (
            <Tooltip title="Cerrar sesión">
              <IconButton color="inherit" onClick={logout} size="small" sx={{ ml: 0.5 }}>
                <LogoutIcon />
              </IconButton>
            </Tooltip>
          )}
        </Toolbar>
      </AppBar>

      <Box
        component="main"
        sx={{
          flexGrow: 1,
          bgcolor: 'background.default',
          p: { xs: 1.5, sm: 2, md: 3 },
        }}
      >
        {children}
      </Box>
    </Box>
  );
}
