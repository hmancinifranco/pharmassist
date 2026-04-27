import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Chip from '@mui/material/Chip';
import IconButton from '@mui/material/IconButton';
import Link from '@mui/material/Link';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import LocationOnIcon from '@mui/icons-material/LocationOn';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import type { VisitaPlanificada } from '../../types';
import { buildGoogleMapsUrl } from '../../utils/mapsUtils';

interface TarjetaVisitasHoyProps {
  visits: VisitaPlanificada[];
  loading: boolean;
  error?: string | null;
  onRetry?: () => void;
  onComplete?: (fechaPlanificada: string, medicoMn: number) => void;
}

function LoadingSkeleton() {
  return (
    <Stack spacing={1.5}>
      {[0, 1, 2].map((i) => (
        <Box key={i}>
          <Skeleton variant="text" width="60%" height={24} />
          <Skeleton variant="text" width="80%" height={20} />
          <Skeleton variant="text" width="40%" height={20} />
        </Box>
      ))}
    </Stack>
  );
}

function EmptyState() {
  return (
    <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
      No tenés visitas planificadas para este mes
    </Typography>
  );
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

export default function TarjetaVisitasHoy({ visits, loading, error, onRetry, onComplete }: TarjetaVisitasHoyProps) {
  const todayStr = new Date().toISOString().slice(0, 10);

  const buildAddress = (v: VisitaPlanificada): string | null => {
    const medico = v.medico;
    if (!medico?.calle && !medico?.altura && !medico?.barrio) return null;
    const parts: string[] = [];
    if (medico.calle) parts.push(medico.calle);
    if (medico.altura) parts.push(medico.altura);
    const street = parts.join(' ');
    return medico.barrio ? `${street}, ${medico.barrio}` : street;
  };

  const getStatusInfo = (visit: VisitaPlanificada) => {
    if (visit.estado === 'Completada') return { color: 'success' as const, label: '✓ Visitado', icon: <CheckCircleIcon fontSize="small" color="success" /> };
    if (visit.fecha_planificada < todayStr) return { color: 'warning' as const, label: 'Vencida', icon: <WarningAmberIcon fontSize="small" color="warning" /> };
    if (visit.fecha_planificada === todayStr) return { color: 'primary' as const, label: 'Hoy', icon: null };
    return { color: 'default' as const, label: 'Pendiente', icon: null };
  };

  return (
    <Card sx={{ flex: 1, minWidth: 0 }}>
      <CardContent>
        <Typography variant="subtitle2" color="text.secondary" gutterBottom>
          Visitas del Mes
        </Typography>

        {loading ? (
          <LoadingSkeleton />
        ) : error ? (
          <ErrorState message={error} onRetry={onRetry} />
        ) : visits.length === 0 ? (
          <EmptyState />
        ) : (
          <List disablePadding sx={{ maxHeight: 420, overflow: 'auto' }}>
            {visits.map((visit, idx) => {
              const medico = visit.medico;
              const doctorName = medico ? `${medico.nombre} ${medico.apellido}` : `MN ${visit.medico_mn}`;
              const address = buildAddress(visit);
              const hasCoords = medico?.latitud != null && medico?.longitud != null;
              const mapsUrl = hasCoords ? buildGoogleMapsUrl(medico!.latitud!, medico!.longitud!) : null;
              const status = getStatusInfo(visit);
              const isCompleted = visit.estado === 'Completada';
              const isPast = visit.fecha_planificada <= todayStr;

              const prevDate = idx > 0 ? visits[idx - 1].fecha_planificada : null;
              const showDateHeader = visit.fecha_planificada !== prevDate;
              const isToday = visit.fecha_planificada === todayStr;

              return (
                <Box key={`${visit.medico_mn}-${idx}`}>
                  {showDateHeader && (
                    <Typography
                      variant="caption"
                      fontWeight={700}
                      color={isToday ? 'primary.main' : 'text.secondary'}
                      sx={{ display: 'block', mt: idx > 0 ? 1.5 : 0, mb: 0.5 }}
                    >
                      {isToday ? '📍 Hoy — ' : ''}{new Date(visit.fecha_planificada + 'T12:00:00').toLocaleDateString('es-AR', { weekday: 'short', day: 'numeric', month: 'short' })}
                    </Typography>
                  )}
                  <ListItem
                    disableGutters
                    sx={{
                      flexDirection: 'column',
                      alignItems: 'flex-start',
                      py: 0.75,
                      opacity: isCompleted ? 0.6 : 1,
                      borderBottom: idx < visits.length - 1 ? '1px solid' : 'none',
                      borderColor: 'divider',
                    }}
                  >
                    <Stack direction="row" alignItems="center" spacing={0.5} sx={{ width: '100%' }}>
                      {status.icon}
                      <Typography variant="body2" fontWeight={600} sx={{ flex: 1, textDecoration: isCompleted ? 'line-through' : 'none' }}>
                        {doctorName}
                      </Typography>
                      {isPast && !isCompleted && onComplete && (
                        <Tooltip title="Marcar como visitado">
                          <IconButton size="small" color="primary" onClick={() => onComplete(visit.fecha_planificada, visit.medico_mn)}>
                            <CheckCircleOutlineIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      )}
                      {isCompleted && <Chip label="Visitado" size="small" color="success" variant="outlined" sx={{ height: 20, fontSize: '0.7rem' }} />}
                      {!isCompleted && isPast && !isToday && <Chip label="Vencida" size="small" color="warning" variant="outlined" sx={{ height: 20, fontSize: '0.7rem' }} />}
                    </Stack>

                    {address && (
                      <Stack direction="row" alignItems="center" spacing={0.5} sx={{ ml: status.icon ? 3 : 0 }}>
                        <LocationOnIcon sx={{ fontSize: 14, color: 'text.secondary' }} />
                        {mapsUrl ? (
                          <Link href={mapsUrl} target="_blank" rel="noopener noreferrer" variant="caption" underline="hover">{address}</Link>
                        ) : (
                          <Typography variant="caption" color="text.secondary">{address}</Typography>
                        )}
                      </Stack>
                    )}

                    {!isCompleted && visit.productos_sugeridos.length > 0 && (
                      <Stack direction="row" spacing={0.5} sx={{ mt: 0.5, flexWrap: 'wrap', gap: 0.5, ml: status.icon ? 3 : 0 }}>
                        {visit.productos_sugeridos.map((prod) => (
                          <Chip key={prod} label={prod} size="small" variant="outlined" color="primary" sx={{ height: 20, fontSize: '0.65rem' }} />
                        ))}
                      </Stack>
                    )}
                  </ListItem>
                </Box>
              );
            })}
          </List>
        )}
      </CardContent>
    </Card>
  );
}
