import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Chip from '@mui/material/Chip';
import Link from '@mui/material/Link';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import type { AlertaSLA } from '../../types';

interface TarjetaAlertasSLAProps {
  alerts: AlertaSLA[];
  loading: boolean;
  error?: string | null;
  onRetry?: () => void;
  onDoctorClick: (medicoMn: number, nombre: string) => void;
}

function LoadingSkeleton() {
  return (
    <Stack spacing={1.5}>
      {[0, 1, 2].map((i) => (
        <Box key={i}>
          <Skeleton variant="text" width="60%" height={24} />
          <Skeleton variant="text" width="80%" height={20} />
          <Stack direction="row" spacing={0.5} sx={{ mt: 0.5 }}>
            <Skeleton variant="rounded" width={70} height={24} />
            <Skeleton variant="rounded" width={50} height={24} />
          </Stack>
        </Box>
      ))}
    </Stack>
  );
}

function EmptyState() {
  return (
    <Stack direction="row" spacing={1} alignItems="center" sx={{ py: 2 }}>
      <CheckCircleOutlineIcon color="success" fontSize="small" />
      <Typography variant="body2" color="text.secondary">
        Todas las visitas están al día. ¡Buen trabajo!
      </Typography>
    </Stack>
  );
}

/** Format ISO date (YYYY-MM-DD) as DD/MM/YYYY */
function formatDate(isoDate?: string): string {
  if (!isoDate) return 'Sin visitas registradas';
  const parts = isoDate.split('-');
  if (parts.length < 3) return isoDate;
  return `${parts[2]}/${parts[1]}/${parts[0]}`;
}

/** Color for days overdue — more overdue = more urgent */
function overdueColor(dias: number): string {
  if (dias >= 60) return '#d32f2f'; // red
  if (dias >= 30) return '#ed6c02'; // orange
  return '#e65100'; // deep orange
}

function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <Alert
      severity="error"
      action={
        onRetry ? (
          <Button color="inherit" size="small" onClick={onRetry}>
            Reintentar
          </Button>
        ) : undefined
      }
      sx={{ mt: 1 }}
    >
      {message}
    </Alert>
  );
}

export default function TarjetaAlertasSLA({
  alerts,
  loading,
  error,
  onRetry,
  onDoctorClick,
}: TarjetaAlertasSLAProps) {
  return (
    <Card sx={{ flex: 1, minWidth: 0 }}>
      <CardContent>
        <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mb: 1 }}>
          <WarningAmberIcon sx={{ fontSize: 18, color: 'warning.main' }} />
          <Typography variant="subtitle2" color="text.secondary">
            Alertas SLA
          </Typography>
        </Stack>

        {loading ? (
          <LoadingSkeleton />
        ) : error ? (
          <ErrorState message={error} onRetry={onRetry} />
        ) : alerts.length === 0 ? (
          <EmptyState />
        ) : (
          <List disablePadding>
            {alerts.map((alert, idx) => {
              const { medico, dias_vencido, cadencia, fecha_ultima_visita } = alert;
              const fullName = `${medico.nombre} ${medico.apellido}`;

              return (
                <ListItem
                  key={medico.medico_mn}
                  disableGutters
                  sx={{
                    flexDirection: 'column',
                    alignItems: 'flex-start',
                    py: 1,
                    borderBottom:
                      idx < alerts.length - 1 ? '1px solid' : 'none',
                    borderColor: 'divider',
                  }}
                >
                  {/* Doctor name — clickable */}
                  <Link
                    component="button"
                    variant="body1"
                    underline="hover"
                    sx={{ fontWeight: 600, textAlign: 'left' }}
                    onClick={() => onDoctorClick(medico.medico_mn, fullName)}
                  >
                    {fullName}
                  </Link>

                  {/* Especialidad + Zona */}
                  <Typography variant="body2" color="text.secondary">
                    {medico.especialidad_medica} · {medico.zona}
                  </Typography>

                  {/* Cadencia chip + last visit date */}
                  <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.5 }}>
                    <Chip
                      label={cadencia}
                      size="small"
                      variant="outlined"
                    />
                    <Typography variant="body2" color="text.secondary">
                      {formatDate(fecha_ultima_visita)}
                    </Typography>
                  </Stack>

                  {/* Days overdue */}
                  <Typography
                    variant="body2"
                    fontWeight={700}
                    sx={{ color: overdueColor(dias_vencido), mt: 0.5 }}
                  >
                    {dias_vencido} días vencido
                  </Typography>
                </ListItem>
              );
            })}
          </List>
        )}
      </CardContent>
    </Card>
  );
}
