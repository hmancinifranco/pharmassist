import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Collapse from '@mui/material/Collapse';
import Link from '@mui/material/Link';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import WhatsAppIcon from '@mui/icons-material/WhatsApp';
import SendIcon from '@mui/icons-material/Send';
import VisibilityIcon from '@mui/icons-material/Visibility';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import type { CumpleañosEntry } from '../../types';
import { buildWhatsAppUrl } from '../../utils/whatsappUtils';

interface TarjetaCumpleanosProps {
  birthdays: CumpleañosEntry[];
  loading: boolean;
  error?: string | null;
  onRetry?: () => void;
  onDoctorClick: (medicoMn: number, nombre: string) => void;
  onGenerateMessage?: (medicoMn: number) => void;
}

function LoadingSkeleton() {
  return (
    <Stack spacing={1.5}>
      {[0, 1, 2].map((i) => (
        <Box key={i}>
          <Skeleton variant="text" width="60%" height={24} />
          <Skeleton variant="text" width="40%" height={20} />
          <Skeleton variant="rounded" width={140} height={32} sx={{ mt: 0.5 }} />
        </Box>
      ))}
    </Stack>
  );
}

function EmptyState() {
  return (
    <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
      No hay cumpleaños próximos en los próximos 30 días
    </Typography>
  );
}

function formatBirthdayDate(isoDate?: string): string {
  if (!isoDate) return '';
  const parts = isoDate.split('-');
  if (parts.length < 3) return '';
  return `${parts[2]}/${parts[1]}`;
}

function diasLabel(dias: number): string {
  if (dias === 0) return '¡Hoy!';
  if (dias === 1) return 'en 1 día';
  return `en ${dias} días`;
}

function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <Alert
      severity="error"
      action={onRetry ? <Button color="inherit" size="small" onClick={onRetry}>Reintentar</Button> : undefined}
      sx={{ mt: 1 }}
    >
      {message}
    </Alert>
  );
}

export default function TarjetaCumpleanos({ birthdays, loading, error, onRetry, onDoctorClick, onGenerateMessage }: TarjetaCumpleanosProps) {
  const [previewMn, setPreviewMn] = useState<number | null>(null);
  const [generatingMn, setGeneratingMn] = useState<number | null>(null);

  return (
    <Card sx={{ flex: 1, minWidth: 0 }}>
      <CardContent>
        <Typography variant="subtitle2" color="text.secondary" gutterBottom>
          Cumpleaños Próximos
        </Typography>

        {loading ? (
          <LoadingSkeleton />
        ) : error ? (
          <ErrorState message={error} onRetry={onRetry} />
        ) : birthdays.length === 0 ? (
          <EmptyState />
        ) : (
          <List disablePadding>
            {birthdays.map((entry, idx) => {
              const { medico, dias_hasta } = entry;
              const fullName = `${medico.nombre} ${medico.apellido}`;
              const hasPhone = !!medico.telefono_celular;
              const hasMessage = !!entry.mensaje_cumpleanos;
              const isPreviewOpen = previewMn === medico.medico_mn;
              const whatsAppUrl = hasPhone && hasMessage
                ? buildWhatsAppUrl(medico.telefono_celular!, entry.mensaje_cumpleanos!)
                : '';

              return (
                <ListItem
                  key={medico.medico_mn}
                  disableGutters
                  sx={{
                    flexDirection: 'column',
                    alignItems: 'flex-start',
                    py: 1,
                    borderBottom: idx < birthdays.length - 1 ? '1px solid' : 'none',
                    borderColor: 'divider',
                  }}
                >
                  <Link
                    component="button"
                    variant="body1"
                    underline="hover"
                    sx={{ fontWeight: 600, textAlign: 'left' }}
                    onClick={() => onDoctorClick(medico.medico_mn, fullName)}
                  >
                    {fullName}
                  </Link>

                  {medico.especialidad_medica && (
                    <Typography variant="body2" color="text.secondary">
                      {medico.especialidad_medica}
                    </Typography>
                  )}

                  <Stack direction="row" spacing={1} alignItems="center">
                    <Typography variant="body2" color="text.secondary">
                      {formatBirthdayDate(medico.fecha_nacimiento)}
                    </Typography>
                    <Typography variant="body2" fontWeight={600} color={dias_hasta === 0 ? 'success.main' : 'primary.main'}>
                      {diasLabel(dias_hasta)}
                    </Typography>
                  </Stack>

                  {/* Action buttons */}
                  <Stack direction="row" spacing={0.5} sx={{ mt: 0.5 }}>
                    {hasMessage && (
                      <Button
                        size="small"
                        variant="text"
                        color="info"
                        startIcon={<VisibilityIcon />}
                        onClick={() => setPreviewMn(isPreviewOpen ? null : medico.medico_mn)}
                        sx={{ textTransform: 'none', fontSize: '0.75rem' }}
                      >
                        {isPreviewOpen ? 'Ocultar' : 'Ver mensaje'}
                      </Button>
                    )}
                    {!hasMessage && (
                      <Button
                        size="small"
                        variant="outlined"
                        color="secondary"
                        startIcon={generatingMn === medico.medico_mn ? undefined : <AutoAwesomeIcon />}
                        disabled={generatingMn === medico.medico_mn}
                        onClick={async () => {
                          setGeneratingMn(medico.medico_mn);
                          if (onGenerateMessage) await onGenerateMessage(medico.medico_mn);
                          setGeneratingMn(null);
                          setPreviewMn(medico.medico_mn);
                        }}
                        sx={{ textTransform: 'none', fontSize: '0.75rem' }}
                      >
                        {generatingMn === medico.medico_mn ? 'Generando con IA...' : 'Generar mensaje'}
                      </Button>
                    )}
                    <Tooltip title={!hasPhone ? 'Sin número de celular registrado' : !hasMessage ? 'Esperando mensaje generado' : ''}>
                      <span>
                        <Button
                          component="a"
                          size="small"
                          variant="outlined"
                          color="success"
                          startIcon={<SendIcon />}
                          endIcon={<WhatsAppIcon />}
                          disabled={!hasPhone || !hasMessage}
                          href={whatsAppUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          sx={{ textTransform: 'none', fontSize: '0.75rem' }}
                        >
                          Enviar
                        </Button>
                      </span>
                    </Tooltip>
                  </Stack>

                  {/* Message preview */}
                  <Collapse in={isPreviewOpen} sx={{ width: '100%' }}>
                    <Box sx={{ mt: 1, p: 1.5, bgcolor: 'action.hover', borderRadius: 1, borderLeft: '3px solid', borderColor: 'success.main' }}>
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                        💬 Mensaje generado por IA:
                      </Typography>
                      <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', fontStyle: 'italic' }}>
                        {entry.mensaje_cumpleanos}
                      </Typography>
                    </Box>
                  </Collapse>
                </ListItem>
              );
            })}
          </List>
        )}
      </CardContent>
    </Card>
  );
}
