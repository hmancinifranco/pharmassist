import Box from '@mui/material/Box';
import IconButton from '@mui/material/IconButton';
import Typography from '@mui/material/Typography';
import Fade from '@mui/material/Fade';
import CloseIcon from '@mui/icons-material/Close';
import MicIcon from '@mui/icons-material/Mic';
import MicOffIcon from '@mui/icons-material/MicOff';
import ParticleSphere, { type VoiceState } from './ParticleSphere';

const STATUS_LABELS: Record<VoiceState | 'connecting', string> = {
  idle: '',
  connecting: 'Conectando...',
  listening: 'Escuchando...',
  thinking: 'Pensando...',
  speaking: 'Respondiendo...',
};

interface VoiceOverlayProps {
  open: boolean;
  state: VoiceState | 'connecting';
  audioLevel: number;
  muted: boolean;
  onClose: () => void;
  onToggleMute: () => void;
}

export default function VoiceOverlay({
  open,
  state,
  audioLevel,
  muted,
  onClose,
  onToggleMute,
}: VoiceOverlayProps) {
  // Map 'connecting' to 'idle' for the sphere animation
  const sphereState: VoiceState = state === 'connecting' ? 'idle' : state;

  return (
    <Fade in={open} timeout={300}>
      <Box
        role="dialog"
        aria-label="Modo voz del asistente"
        sx={{
          position: 'fixed',
          inset: 0,
          zIndex: 1400,
          display: open ? 'flex' : 'none',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          bgcolor: 'rgba(10, 15, 30, 0.95)',
          backdropFilter: 'blur(12px)',
        }}
      >
        {/* Particle sphere */}
        <Box sx={{ mb: 3 }}>
          <ParticleSphere state={sphereState} audioLevel={audioLevel} size={280} />
        </Box>

        {/* Status text */}
        <Typography
          variant="body1"
          sx={{
            color: 'rgba(255,255,255,0.7)',
            fontSize: '1.1rem',
            minHeight: 28,
            letterSpacing: 0.5,
          }}
        >
          {STATUS_LABELS[state]}
        </Typography>

        {/* Bottom controls */}
        <Box
          sx={{
            position: 'absolute',
            bottom: 48,
            left: 0,
            right: 0,
            display: 'flex',
            justifyContent: 'center',
            gap: 6,
          }}
        >
          {/* Close / hangup */}
          <IconButton
            onClick={onClose}
            aria-label="Cerrar modo voz"
            sx={{
              width: 56,
              height: 56,
              bgcolor: 'rgba(255,255,255,0.1)',
              color: '#fff',
              '&:hover': { bgcolor: 'rgba(255,80,80,0.3)' },
            }}
          >
            <CloseIcon fontSize="large" />
          </IconButton>

          {/* Mute / unmute */}
          <IconButton
            onClick={onToggleMute}
            aria-label={muted ? 'Activar micrófono' : 'Silenciar micrófono'}
            sx={{
              width: 56,
              height: 56,
              bgcolor: muted ? 'rgba(255,80,80,0.25)' : 'rgba(255,255,255,0.1)',
              color: muted ? '#ff5252' : '#fff',
              '&:hover': {
                bgcolor: muted ? 'rgba(255,80,80,0.4)' : 'rgba(255,255,255,0.2)',
              },
            }}
          >
            {muted ? <MicOffIcon fontSize="large" /> : <MicIcon fontSize="large" />}
          </IconButton>
        </Box>
      </Box>
    </Fade>
  );
}
