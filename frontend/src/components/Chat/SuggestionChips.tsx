import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import LightbulbOutlinedIcon from '@mui/icons-material/LightbulbOutlined';

const SUGGESTIONS = [
  '¿Qué visitas tengo hoy?',
  '¿Qué médicos tienen cumpleaños esta semana?',
  '¿Cuáles son mis alertas SLA?',
  'Dame un resumen de ventas de mi zona',
];

interface SuggestionChipsProps {
  onChipClick: (text: string) => void;
  visible: boolean;
}

export function SuggestionChips({ onChipClick, visible }: SuggestionChipsProps) {
  if (!visible) return null;
  return (
    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ p: 1 }}>
      {SUGGESTIONS.map((text) => (
        <Chip
          key={text}
          label={text}
          onClick={() => onChipClick(text)}
          variant="outlined"
          color="primary"
          clickable
          size="small"
          data-testid="suggestion-chip"
          icon={<LightbulbOutlinedIcon />}
        />
      ))}
    </Stack>
  );
}
