import { useState, useMemo } from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Collapse from '@mui/material/Collapse';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import CodeIcon from '@mui/icons-material/Code';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import LightbulbOutlinedIcon from '@mui/icons-material/LightbulbOutlined';
import { DataGrid, type GridColDef } from '@mui/x-data-grid';
import { LineChart } from '@mui/x-charts/LineChart';
import { BarChart } from '@mui/x-charts/BarChart';
import type { StructuredData, TableData, ChartData } from '../../types/agent';

// ─────────────────────────────────────────────────────────────────────────────
// Props
// ─────────────────────────────────────────────────────────────────────────────

interface StructuredResponseProps {
  structured: StructuredData;
  onSuggestionClick?: (suggestion: string) => void;
}

// ─────────────────────────────────────────────────────────────────────────────
// DataGrid Section
// ─────────────────────────────────────────────────────────────────────────────

function DataGridSection({ table }: { table: TableData }) {
  const columns: GridColDef[] = useMemo(
    () =>
      table.columns.map((col) => ({
        field: col,
        headerName: col,
        flex: 1,
        minWidth: 100,
        sortable: true,
      })),
    [table.columns],
  );

  const rows = useMemo(
    () =>
      table.rows.map((row, index) => ({
        id: (row as Record<string, unknown>).id ?? index,
        ...row,
      })),
    [table.rows],
  );

  return (
    <Paper variant="outlined" sx={{ maxHeight: 400, width: '100%', mb: 1 }}>
      <DataGrid
        rows={rows}
        columns={columns}
        density="compact"
        pageSizeOptions={[10, 25]}
        initialState={{
          pagination: { paginationModel: { pageSize: 10 } },
        }}
        autoHeight
        disableRowSelectionOnClick
        sx={{
          border: 'none',
          '& .MuiDataGrid-columnHeaders': {
            bgcolor: 'action.hover',
          },
          fontSize: '0.8rem',
        }}
      />
    </Paper>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Chart Section
// ─────────────────────────────────────────────────────────────────────────────

type ChartDataset = Record<string, string | number | Date | null | undefined>[];

function ChartSection({ chart, data }: { chart: ChartData; data: Record<string, unknown>[] }) {
  const dataset = useMemo(
    () => data as ChartDataset,
    [data],
  );

  const series = useMemo(
    () =>
      chart.series.map((s) => ({
        dataKey: s.dataKey,
        label: s.label,
      })),
    [chart.series],
  );

  const xAxis = useMemo(
    () => [{ scaleType: 'band' as const, dataKey: chart.xAxis }],
    [chart.xAxis],
  );

  return (
    <Paper variant="outlined" sx={{ p: 1, mb: 1, width: '100%' }}>
      {chart.type === 'line' ? (
        <LineChart
          dataset={dataset}
          height={250}
          xAxis={xAxis}
          series={series}
        />
      ) : (
        <BarChart
          dataset={dataset}
          height={250}
          xAxis={xAxis}
          series={series}
        />
      )}
    </Paper>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Data provenance helpers — derive a human-readable summary from the SQL
// ─────────────────────────────────────────────────────────────────────────────

/** Extract the table names referenced in FROM / JOIN clauses. */
function extractTables(sql: string): string[] {
  const tables = new Set<string>();
  const regex = /\b(?:from|join)\s+([a-z_][\w."]*)/gi;
  let match: RegExpExecArray | null;
  while ((match = regex.exec(sql)) !== null) {
    // Strip schema prefix and quotes, keep the bare table name
    const raw = match[1].replace(/"/g, '').split('.').pop() ?? '';
    if (raw) tables.add(raw);
  }
  return [...tables];
}

/** Detect the aggregation / operation keywords used in the query. */
function extractOperations(sql: string): string[] {
  const ops: string[] = [];
  const upper = sql.toUpperCase();
  if (/\bGROUP\s+BY\b/.test(upper)) ops.push('agrupación');
  if (/\bCOUNT\s*\(/.test(upper)) ops.push('conteo');
  if (/\bSUM\s*\(/.test(upper)) ops.push('suma');
  if (/\bAVG\s*\(/.test(upper)) ops.push('promedio');
  if (/\bMAX\s*\(/.test(upper)) ops.push('máximo');
  if (/\bMIN\s*\(/.test(upper)) ops.push('mínimo');
  if (/\bORDER\s+BY\b/.test(upper)) ops.push('ordenamiento');
  if (/\bJOIN\b/.test(upper)) ops.push('cruce de tablas');
  return ops;
}

// ─────────────────────────────────────────────────────────────────────────────
// Data Provenance Section (collapsible "de dónde salió esto")
// ─────────────────────────────────────────────────────────────────────────────

function SqlSection({
  sql,
  rowCount,
  show,
  onToggle,
}: {
  sql: string;
  rowCount?: number;
  show: boolean;
  onToggle: () => void;
}) {
  const tables = useMemo(() => extractTables(sql), [sql]);
  const operations = useMemo(() => extractOperations(sql), [sql]);

  return (
    <Box sx={{ mb: 1 }}>
      <Button
        size="small"
        startIcon={<CodeIcon />}
        endIcon={show ? <ExpandLessIcon /> : <ExpandMoreIcon />}
        onClick={onToggle}
        sx={{ textTransform: 'none', fontSize: '0.75rem' }}
      >
        ¿De dónde salió esto?
      </Button>
      <Collapse in={show}>
        <Box
          sx={{
            mt: 0.5,
            p: 1.5,
            bgcolor: 'action.hover',
            borderRadius: 1,
            fontSize: '0.75rem',
          }}
        >
          {/* Human-readable provenance summary */}
          <Stack spacing={0.75} sx={{ mb: 1.5 }}>
            {tables.length > 0 && (
              <Box>
                <Typography variant="caption" color="text.secondary">
                  Datos consultados en:
                </Typography>
                <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.25 }}>
                  {tables.map((t) => (
                    <Chip key={t} label={t} size="small" variant="outlined" />
                  ))}
                </Stack>
              </Box>
            )}
            {operations.length > 0 && (
              <Box>
                <Typography variant="caption" color="text.secondary">
                  Operaciones aplicadas:
                </Typography>
                <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mt: 0.25 }}>
                  {operations.map((op) => (
                    <Chip key={op} label={op} size="small" color="primary" variant="outlined" />
                  ))}
                </Stack>
              </Box>
            )}
            {typeof rowCount === 'number' && (
              <Typography variant="caption" color="text.secondary">
                {rowCount} {rowCount === 1 ? 'registro' : 'registros'} devuelto
                {rowCount === 1 ? '' : 's'} por la consulta.
              </Typography>
            )}
          </Stack>

          {/* Raw SQL */}
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
            Consulta SQL ejecutada:
          </Typography>
          <Box
            sx={{
              p: 1.5,
              bgcolor: 'grey.100',
              borderRadius: 1,
              fontFamily: 'monospace',
              fontSize: '0.72rem',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              overflow: 'auto',
              maxHeight: 200,
            }}
          >
            {sql}
          </Box>
        </Box>
      </Collapse>
    </Box>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Suggestions Section
// ─────────────────────────────────────────────────────────────────────────────

function SuggestionsSection({
  suggestions,
  onClick,
}: {
  suggestions: string[];
  onClick?: (suggestion: string) => void;
}) {
  return (
    <Box sx={{ mt: 0.5 }}>
      <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: 'block' }}>
        Sugerencias
      </Typography>
      <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
        {suggestions.map((suggestion, i) => (
          <Chip
            key={i}
            label={suggestion}
            size="small"
            variant="outlined"
            color="primary"
            icon={<LightbulbOutlinedIcon />}
            onClick={() => onClick?.(suggestion)}
            clickable
          />
        ))}
      </Stack>
    </Box>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main Component
// ─────────────────────────────────────────────────────────────────────────────

export function StructuredResponse({ structured, onSuggestionClick }: StructuredResponseProps) {
  const [showSql, setShowSql] = useState(false);

  return (
    <Box sx={{ mt: 1, width: '100%' }}>
      {/* Table */}
      {structured.table && structured.table.rows.length > 2 && (
        <DataGridSection table={structured.table} />
      )}

      {/* Chart */}
      {structured.chart && structured.table && (
        <ChartSection chart={structured.chart} data={structured.table.rows} />
      )}

      {/* Data provenance toggle */}
      {structured.sql && (
        <SqlSection
          sql={structured.sql}
          rowCount={structured.table?.rows.length}
          show={showSql}
          onToggle={() => setShowSql(!showSql)}
        />
      )}

      {/* Suggestions */}
      {structured.suggestions && structured.suggestions.length > 0 && (
        <SuggestionsSection suggestions={structured.suggestions} onClick={onSuggestionClick} />
      )}
    </Box>
  );
}
