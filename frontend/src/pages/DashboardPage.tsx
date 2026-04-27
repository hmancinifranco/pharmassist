import { useEffect, useState, useCallback, useRef, useMemo } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Snackbar from '@mui/material/Snackbar';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useTheme } from '@mui/material/styles';
import TarjetaVisitasHoy from '../components/Cards/TarjetaVisitasHoy';
import TarjetaCumpleanos from '../components/Cards/TarjetaCumpleanos';
import TarjetaAlertasSLA from '../components/Cards/TarjetaAlertasSLA';
import ChatPanel from '../components/Chat/ChatPanel';
import FABChat from '../components/Chat/FABChat';
import GrabadorAudio from '../components/Audio/GrabadorAudio';
import VoiceOverlay from '../components/Voice/VoiceOverlay';
import { VoiceService } from '../api/voice';
import type { VoiceState } from '../components/Voice/ParticleSphere';
import useAppStore from '../stores/useAppStore';
import useAuthStore from '../stores/useAuthStore';
import v2vImg from '../assets/voice.png';

const DRAG_THRESHOLD = 5;

export default function DashboardPage() {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const [chatOpen, setChatOpen] = useState(false);
  const [snackbar, setSnackbar] = useState<string | null>(null);

  // Voice mode state
  const [voiceOpen, setVoiceOpen] = useState(false);
  const [voiceState, setVoiceState] = useState<VoiceState | 'connecting'>('idle');
  const [audioLevel, setAudioLevel] = useState(0);
  const [muted, setMuted] = useState(false);
  const voiceServiceRef = useRef<VoiceService | null>(null);
  const getIdToken = useAuthStore((s) => s.getIdToken);
  const apmId = useAuthStore((s) => s.apmId);

  const visits = useAppStore((s) => s.visits);
  const visitsLoading = useAppStore((s) => s.visitsLoading);
  const visitsError = useAppStore((s) => s.visitsError);
  const fetchVisitsToday = useAppStore((s) => s.fetchVisitsToday);
  const completeVisit = useAppStore((s) => s.completeVisit);

  const birthdays = useAppStore((s) => s.birthdays);
  const birthdaysLoading = useAppStore((s) => s.birthdaysLoading);
  const birthdaysError = useAppStore((s) => s.birthdaysError);
  const fetchBirthdays = useAppStore((s) => s.fetchBirthdays);
  const generateBirthdayMessage = useAppStore((s) => s.generateBirthdayMessage);

  const alerts = useAppStore((s) => s.alerts);
  const alertsLoading = useAppStore((s) => s.alertsLoading);
  const alertsError = useAppStore((s) => s.alertsError);
  const fetchSlaAlerts = useAppStore((s) => s.fetchSlaAlerts);

  const sendMessage = useAppStore((s) => s.sendMessage);

  // --- Draggable voice FAB state ---
  const voiceFabSize = isMobile ? 56 : 64;
  const [voiceFabPos, setVoiceFabPos] = useState({ x: isMobile ? 80 : 24, y: 24 });
  const voiceDragging = useRef(false);
  const voiceWasDragged = useRef(false);
  const voiceOffset = useRef({ x: 0, y: 0 });
  const voiceStartPos = useRef({ x: 0, y: 0 });

  const onVoicePointerDown = useCallback(
    (e: React.PointerEvent) => {
      voiceDragging.current = true;
      voiceWasDragged.current = false;
      voiceStartPos.current = { x: e.clientX, y: e.clientY };
      voiceOffset.current = {
        x: e.clientX - (window.innerWidth - voiceFabPos.x - voiceFabSize),
        y: e.clientY - (window.innerHeight - voiceFabPos.y - voiceFabSize),
      };
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
    },
    [voiceFabPos, voiceFabSize],
  );

  const onVoicePointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!voiceDragging.current) return;
      const dx = e.clientX - voiceStartPos.current.x;
      const dy = e.clientY - voiceStartPos.current.y;
      if (Math.abs(dx) > DRAG_THRESHOLD || Math.abs(dy) > DRAG_THRESHOLD) {
        voiceWasDragged.current = true;
      }
      const newX = window.innerWidth - (e.clientX - voiceOffset.current.x) - voiceFabSize;
      const newY = window.innerHeight - (e.clientY - voiceOffset.current.y) - voiceFabSize;
      setVoiceFabPos({
        x: Math.max(8, Math.min(newX, window.innerWidth - voiceFabSize - 8)),
        y: Math.max(8, Math.min(newY, window.innerHeight - voiceFabSize - 8)),
      });
    },
    [voiceFabSize],
  );

  const medicosFromVisits = useMemo(() => {
    const seen = new Set<number>();
    return visits
      .filter((v) => v.medico && !seen.has(v.medico.medico_mn) && seen.add(v.medico.medico_mn))
      .map((v) => v.medico!);
  }, [visits]);

  const handleOpenVoice = useCallback(async () => {
    const token = getIdToken();
    if (!token) return;

    setVoiceOpen(true);
    setVoiceState('connecting');
    setMuted(false);
    setAudioLevel(0);

    const service = new VoiceService(token, apmId, {
      onStateChange: (s) => setVoiceState(s),
      onAudioLevel: (l) => setAudioLevel(l),
      onError: (msg) => setSnackbar(msg),
      onDisconnect: () => {
        setVoiceOpen(false);
        setVoiceState('idle');
        setAudioLevel(0);
      },
    });
    voiceServiceRef.current = service;
    await service.connect();
    setVoiceState('listening');
  }, [getIdToken, apmId]);

  const onVoicePointerUp = useCallback(() => {
    voiceDragging.current = false;
    if (!voiceWasDragged.current) void handleOpenVoice();
  }, [handleOpenVoice]);

  const handleCloseVoice = useCallback(() => {
    voiceServiceRef.current?.disconnect();
    voiceServiceRef.current = null;
    setVoiceOpen(false);
    setVoiceState('idle');
    setAudioLevel(0);
  }, []);

  const handleToggleMute = useCallback(() => {
    setMuted((prev) => {
      const next = !prev;
      voiceServiceRef.current?.setMuted(next);
      return next;
    });
  }, []);

  const handleDoctorClick = (medicoMn: number, nombre: string) => {
    void medicoMn;
    sendMessage(`Dame un brief sobre el Dr. ${nombre}`);
    if (isMobile) setChatOpen(true);
  };

  // Show snackbar for any card error
  useEffect(() => {
    const error = visitsError || birthdaysError || alertsError;
    if (error) setSnackbar(error);
  }, [visitsError, birthdaysError, alertsError]);

  useEffect(() => {
    fetchVisitsToday();
    fetchBirthdays();
    fetchSlaAlerts();
  }, [fetchVisitsToday, fetchBirthdays, fetchSlaAlerts]);

  const handleRetry = () => {
    setSnackbar(null);
    fetchVisitsToday();
    fetchBirthdays();
    fetchSlaAlerts();
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, height: '100%' }}>
      {/* Tarjetas Contextuales */}
      <Stack direction={isMobile ? 'column' : 'row'} spacing={2} sx={{ width: '100%' }}>
        <TarjetaVisitasHoy
          visits={visits}
          loading={visitsLoading}
          error={visitsError}
          onRetry={fetchVisitsToday}
          onComplete={completeVisit}
        />
        <TarjetaCumpleanos
          birthdays={birthdays}
          loading={birthdaysLoading}
          error={birthdaysError}
          onRetry={fetchBirthdays}
          onDoctorClick={handleDoctorClick}
          onGenerateMessage={generateBirthdayMessage}
        />
        <TarjetaAlertasSLA
          alerts={alerts}
          loading={alertsLoading}
          error={alertsError}
          onRetry={fetchSlaAlerts}
          onDoctorClick={handleDoctorClick}
        />
      </Stack>

      {/* Minuta Rápida */}
      <Box>
        <Typography variant="h6" sx={{ mb: 1 }}>
          Minuta Rápida
        </Typography>
        <GrabadorAudio medicos={medicosFromVisits} />
      </Box>

      {/* Chat Panel — visible on desktop, hidden on mobile (accessible via FAB) */}
      {!isMobile && <ChatPanel />}

      {/* FAB + Drawer — mobile only */}
      {isMobile && (
        <FABChat
          open={chatOpen}
          onOpen={() => setChatOpen(true)}
          onClose={() => setChatOpen(false)}
        />
      )}

      {/* Error snackbar with retry */}
      <Snackbar
        open={!!snackbar}
        autoHideDuration={10000}
        onClose={() => setSnackbar(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          severity="error"
          onClose={() => setSnackbar(null)}
          action={
            <Button color="inherit" size="small" onClick={handleRetry}>
              Reintentar
            </Button>
          }
        >
          {snackbar}
        </Alert>
      </Snackbar>

      {/* Voice mode FAB — draggable with custom image */}
      <Box
        onPointerDown={onVoicePointerDown}
        onPointerMove={onVoicePointerMove}
        onPointerUp={onVoicePointerUp}
        role="button"
        aria-label="Activar modo voz"
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') void handleOpenVoice(); }}
        sx={{
          position: 'fixed',
          bottom: voiceFabPos.y,
          right: voiceFabPos.x,
          zIndex: 1300,
          width: voiceFabSize,
          height: voiceFabSize,
          borderRadius: '50%',
          overflow: 'hidden',
          cursor: 'grab',
          touchAction: 'none',
          userSelect: 'none',
          boxShadow: 4,
          transition: voiceDragging.current ? 'none' : 'box-shadow 0.2s',
          '&:hover': { boxShadow: 8 },
          '&:active': { cursor: 'grabbing' },
        }}
      >
        <img
          src={v2vImg}
          alt="Activar modo voz"
          draggable={false}
          style={{ width: '100%', height: '100%', objectFit: 'cover', pointerEvents: 'none' }}
        />
      </Box>

      {/* Voice overlay */}
      <VoiceOverlay
        open={voiceOpen}
        state={voiceState}
        audioLevel={audioLevel}
        muted={muted}
        onClose={handleCloseVoice}
        onToggleMute={handleToggleMute}
      />
    </Box>
  );
}
