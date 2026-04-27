import { useState, useRef, useCallback } from 'react';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import Divider from '@mui/material/Divider';
import IconButton from '@mui/material/IconButton';
import LinearProgress from '@mui/material/LinearProgress';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import MicIcon from '@mui/icons-material/Mic';
import StopIcon from '@mui/icons-material/Stop';
import DeleteIcon from '@mui/icons-material/Delete';
import SaveIcon from '@mui/icons-material/Save';
import ReplayIcon from '@mui/icons-material/Replay';
import type { Medico, MinutaVisita } from '../../types';
import {
  uploadAudio,
  saveMinuta,
} from '../../api/client';
import useAppStore from '../../stores/useAppStore';

const MIN_DURATION_S = 3;

type ProcessingStep = 'idle' | 'recording' | 'recorded' | 'uploading' | 'transcribing' | 'summarizing' | 'preview' | 'saved';

const STEP_LABELS: Record<ProcessingStep, string> = {
  idle: '',
  recording: 'Grabando…',
  recorded: '',
  uploading: 'Subiendo audio…',
  transcribing: 'Transcribiendo…',
  summarizing: 'Generando resumen…',
  preview: '',
  saved: '',
};

interface GrabadorAudioProps {
  /** Médicos from the APM's portfolio for selection */
  medicos?: Medico[];
}

export default function GrabadorAudio({ medicos = [] }: GrabadorAudioProps) {
  const apmId = useAppStore((s) => s.apmId);

  // Recording state
  const [step, setStep] = useState<ProcessingStep>('idle');
  const [error, setError] = useState<string | null>(null);
  const [selectedMedico, setSelectedMedico] = useState<Medico | null>(null);
  const [audioSupported, setAudioSupported] = useState(true);

  // Audio refs
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const startTimeRef = useRef<number>(0);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [duration, setDuration] = useState(0);

  // Minuta preview
  const [minuta, setMinuta] = useState<MinutaVisita | null>(null);
  const [transcription, setTranscription] = useState('');

  const isProcessing = step === 'uploading' || step === 'transcribing' || step === 'summarizing';

  const cleanup = useCallback(() => {
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    setAudioBlob(null);
    setAudioUrl(null);
    setDuration(0);
    setMinuta(null);
    setTranscription('');
    setError(null);
  }, [audioUrl]);

  /* ── Start recording ─────────────────────────────────────────────────── */
  const startRecording = async () => {
    cleanup();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const elapsed = (Date.now() - startTimeRef.current) / 1000;
        setDuration(elapsed);

        if (elapsed < MIN_DURATION_S) {
          setError('La grabación es muy corta. Grabá al menos 3 segundos.');
          setStep('idle');
          return;
        }

        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        const url = URL.createObjectURL(blob);
        setAudioBlob(blob);
        setAudioUrl(url);
        setStep('recorded');
      };

      mediaRecorderRef.current = recorder;
      startTimeRef.current = Date.now();
      recorder.start();
      setStep('recording');
      setError(null);
    } catch {
      setAudioSupported(false);
      setError('Tu navegador no soporta grabación de audio.');
    }
  };

  /* ── Stop recording ──────────────────────────────────────────────────── */
  const stopRecording = () => {
    mediaRecorderRef.current?.stop();
  };

  /* ── Upload and transcribe directly ────────────────────────────────── */
  const handleUploadDirect = async () => {
    if (!audioBlob || !selectedMedico) return;
    setStep('uploading');
    setError(null);

    try {
      const res = await uploadAudio(audioBlob, selectedMedico.medico_mn);
      setTranscription(res.transcription);
      setMinuta(res.minuta_draft);
      setStep('preview');
    } catch {
      setError('No se pudo transcribir el audio. Intentá de nuevo.');
      setStep('recorded');
    }
  };

  /* ── Save minuta ─────────────────────────────────────────────────────── */
  const handleSave = async () => {
    if (!minuta || !selectedMedico) return;
    try {
      // If minuta already has an ID (from pipeline), it's already saved
      if (minuta.minuta_id) {
        setStep('saved');
        return;
      }
      await saveMinuta(selectedMedico.medico_mn, apmId, minuta);
      setStep('saved');
    } catch {
      setError('No se pudo guardar la minuta. Intentá de nuevo.');
    }
  };

  /* ── Discard & reset ─────────────────────────────────────────────────── */
  const handleDiscard = () => {
    cleanup();
    setStep('idle');
  };

  /* ── Format duration ─────────────────────────────────────────────────── */
  const fmtDuration = (s: number) => {
    const mins = Math.floor(s / 60);
    const secs = Math.floor(s % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  /* ── Render ──────────────────────────────────────────────────────────── */
  return (
    <Card>
      <CardContent>

        {/* Médico selector */}
        <Autocomplete
          options={medicos}
          getOptionLabel={(m) => `${m.nombre} ${m.apellido} — ${m.especialidad_medica}`}
          value={selectedMedico}
          onChange={(_, v) => setSelectedMedico(v)}
          renderInput={(params) => (
            <TextField {...params} label="Médico asociado" size="small" />
          )}
          isOptionEqualToValue={(opt, val) => opt.medico_mn === val.medico_mn}
          disabled={isProcessing || step === 'saved' || !audioSupported}
          sx={{ mb: 2 }}
        />

        {/* Error alert */}
        {error && (
          <Alert severity="error" sx={{ mb: 1 }} onClose={audioSupported ? () => setError(null) : undefined}>
            {error}
          </Alert>
        )}

        {/* Audio not supported — hide recorder */}
        {!audioSupported ? null : (
          <>
        {/* Recording controls */}
        {(step === 'idle' || step === 'recording') && (
          <Stack direction="row" spacing={2} alignItems="center">
            {step === 'idle' ? (
              <IconButton
                color="error"
                onClick={startRecording}
                aria-label="Grabar audio"
                sx={{
                  bgcolor: 'error.light',
                  color: 'white',
                  '&:hover': { bgcolor: 'error.main' },
                }}
              >
                <MicIcon />
              </IconButton>
            ) : (
              <IconButton
                color="error"
                onClick={stopRecording}
                aria-label="Detener grabación"
                sx={{
                  bgcolor: 'error.main',
                  color: 'white',
                  animation: 'pulse 1.5s infinite',
                  '@keyframes pulse': {
                    '0%': { boxShadow: '0 0 0 0 rgba(211,47,47,0.4)' },
                    '70%': { boxShadow: '0 0 0 10px rgba(211,47,47,0)' },
                    '100%': { boxShadow: '0 0 0 0 rgba(211,47,47,0)' },
                  },
                  '&:hover': { bgcolor: 'error.dark' },
                }}
              >
                <StopIcon />
              </IconButton>
            )}
            <Typography variant="body2" color="text.secondary">
              {step === 'recording'
                ? 'Grabando… tocá para detener'
                : 'Tocá para grabar'}
            </Typography>
          </Stack>
        )}

        {/* Audio preview + upload buttons */}
        {step === 'recorded' && audioUrl && (
          <Stack spacing={1.5}>
            <Stack direction="row" spacing={1} alignItems="center">
              <audio src={audioUrl} controls style={{ flexGrow: 1, height: 36 }} />
              <Typography variant="caption" color="text.secondary">
                {fmtDuration(duration)}
              </Typography>
            </Stack>
            <Stack direction="row" spacing={1}>
              <Button
                variant="contained"
                size="small"
                onClick={handleUploadDirect}
                disabled={!selectedMedico}
                startIcon={<SaveIcon />}
              >
                Transcribir y resumir
              </Button>
              <Button
                variant="outlined"
                size="small"
                color="error"
                onClick={handleDiscard}
                startIcon={<DeleteIcon />}
              >
                Descartar
              </Button>
            </Stack>
            {!selectedMedico && (
              <Typography variant="caption" color="text.secondary">
                Seleccioná un médico antes de procesar
              </Typography>
            )}
          </Stack>
        )}

        {/* Processing states */}
        {isProcessing && (
          <Stack spacing={1.5} sx={{ py: 2 }}>
            <Stack direction="row" spacing={1.5} alignItems="center">
              <CircularProgress size={24} />
              <Typography variant="body2" color="text.secondary">
                {STEP_LABELS[step]}
              </Typography>
            </Stack>
            <LinearProgress
              variant="indeterminate"
              sx={{ borderRadius: 1 }}
            />
            <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
              {(['uploading', 'transcribing', 'summarizing'] as const).map((s) => (
                <Chip
                  key={s}
                  label={STEP_LABELS[s]}
                  size="small"
                  color={step === s ? 'primary' : 'default'}
                  variant={step === s ? 'filled' : 'outlined'}
                />
              ))}
            </Stack>
          </Stack>
        )}

        {/* Minuta preview */}
        {step === 'preview' && minuta && (
          <Stack spacing={1.5}>
            <Divider />
            <Typography variant="subtitle2">Minuta generada</Typography>

            {transcription && (
              <Box>
                <Typography variant="caption" color="text.secondary">
                  Transcripción
                </Typography>
                <Typography variant="body2" sx={{ fontStyle: 'italic' }}>
                  {transcription}
                </Typography>
              </Box>
            )}

            <Box>
              <Typography variant="caption" color="text.secondary">
                Resumen
              </Typography>
              <Typography variant="body2">{minuta.resumen}</Typography>
            </Box>

            {minuta.productos_discutidos.length > 0 && (
              <Box>
                <Typography variant="caption" color="text.secondary">
                  Productos discutidos
                </Typography>
                <Stack direction="row" spacing={0.5} sx={{ mt: 0.5, flexWrap: 'wrap', gap: 0.5 }}>
                  {minuta.productos_discutidos.map((p) => (
                    <Chip key={p} label={p} size="small" variant="outlined" color="primary" />
                  ))}
                </Stack>
              </Box>
            )}

            {minuta.compromisos && (
              <Box>
                <Typography variant="caption" color="text.secondary">
                  Compromisos
                </Typography>
                <Typography variant="body2">{minuta.compromisos}</Typography>
              </Box>
            )}

            {minuta.proximos_pasos && (
              <Box>
                <Typography variant="caption" color="text.secondary">
                  Próximos pasos
                </Typography>
                <Typography variant="body2">{minuta.proximos_pasos}</Typography>
              </Box>
            )}

            <Stack direction="row" spacing={1}>
              <Button
                variant="contained"
                size="small"
                onClick={handleSave}
                startIcon={<SaveIcon />}
              >
                {minuta.minuta_id ? 'Confirmar minuta' : 'Guardar minuta'}
              </Button>
              <Button
                variant="outlined"
                size="small"
                onClick={handleDiscard}
                startIcon={<ReplayIcon />}
              >
                Volver a grabar
              </Button>
            </Stack>
          </Stack>
        )}

        {/* Saved confirmation */}
        {step === 'saved' && (
          <Stack spacing={1.5}>
            <Alert severity="success">Minuta guardada correctamente.</Alert>
            <Button variant="outlined" size="small" onClick={handleDiscard}>
              Grabar otra nota
            </Button>
          </Stack>
        )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
