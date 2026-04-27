import Box from '@mui/material/Box';
import Drawer from '@mui/material/Drawer';
import IconButton from '@mui/material/IconButton';
import CloseIcon from '@mui/icons-material/Close';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useTheme } from '@mui/material/styles';
import ChatPanel from './ChatPanel';
import taImg from '../../assets/text.png';

interface FABChatProps {
  open: boolean;
  onOpen: () => void;
  onClose: () => void;
}

export default function FABChat({ open, onOpen, onClose }: FABChatProps) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const size = isMobile ? 56 : 64;

  return (
    <>
      <Box
        onClick={onOpen}
        role="button"
        aria-label="Abrir chat"
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onOpen(); }}
        sx={{
          position: 'fixed',
          bottom: 24,
          right: 24,
          zIndex: theme.zIndex.fab,
          width: size,
          height: size,
          borderRadius: '50%',
          overflow: 'hidden',
          cursor: 'pointer',
          boxShadow: 4,
          transition: 'box-shadow 0.2s, transform 0.15s',
          '&:hover': { boxShadow: 8, transform: 'scale(1.05)' },
          '&:active': { transform: 'scale(0.95)' },
        }}
      >
        <img
          src={taImg}
          alt="Abrir chat"
          draggable={false}
          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
        />
      </Box>

      <Drawer
        anchor="bottom"
        open={open}
        onClose={onClose}
        PaperProps={{
          sx: { height: '85vh', borderTopLeftRadius: 16, borderTopRightRadius: 16 },
        }}
      >
        <Box sx={{ display: 'flex', justifyContent: 'flex-end', p: 1 }}>
          <IconButton onClick={onClose} aria-label="Cerrar chat">
            <CloseIcon />
          </IconButton>
        </Box>
        <Box sx={{ flexGrow: 1, px: 2, pb: 2, display: 'flex' }}>
          <ChatPanel />
        </Box>
      </Drawer>
    </>
  );
}
