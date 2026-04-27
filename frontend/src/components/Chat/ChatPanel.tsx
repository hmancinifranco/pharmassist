import { useRef, useEffect, useState } from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import IconButton from '@mui/material/IconButton';
import InputAdornment from '@mui/material/InputAdornment';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import SendIcon from '@mui/icons-material/Send';
import PersonIcon from '@mui/icons-material/Person';
import RefreshIcon from '@mui/icons-material/Refresh';
import pillAIIcon from '../../assets/AIPill-2.png';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import useAppStore from '../../stores/useAppStore';
import type { ChatMessage } from '../../types';

/* ── Message bubble ──────────────────────────────────────────────────────── */

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user';

  return (
    <Stack
      direction="row"
      spacing={1}
      sx={{
        justifyContent: isUser ? 'flex-end' : 'flex-start',
        alignItems: 'flex-start',
      }}
    >
      {!isUser && (
        <Box
          component="img"
          src={pillAIIcon}
          alt="PharmAssist"
          sx={{
            mt: 0.5,
            width: 22,
            height: 22,
            flexShrink: 0,
            transform: 'rotate(0deg)',
          }}
        />
      )}

      <Box
        sx={{
          maxWidth: '85%',
          bgcolor: isUser ? undefined : 'action.hover',
          background: isUser
            ? 'linear-gradient(135deg, #1565C0 0%, #1E88E5 60%, #42A5F5 100%)'
            : undefined,
          color: isUser ? '#fff' : 'text.primary',
          borderRadius: 2.5,
          px: 2,
          py: 1,
          '& p': { m: 0 },
          '& p + p': { mt: 1 },
          '& ul, & ol': { my: 0.5, pl: 2.5 },
          '& code': {
            bgcolor: isUser ? 'rgba(255,255,255,0.15)' : 'action.selected',
            borderRadius: 0.5,
            px: 0.5,
            fontSize: '0.85em',
          },
          '& pre': {
            bgcolor: isUser ? 'rgba(0,0,0,0.2)' : 'action.selected',
            borderRadius: 1,
            p: 1,
            overflow: 'auto',
            '& code': { bgcolor: 'transparent', p: 0 },
          },
          '& table': {
            borderCollapse: 'collapse',
            width: '100%',
            my: 1,
            fontSize: '0.8rem',
          },
          '& th': {
            bgcolor: 'action.selected',
            fontWeight: 700,
            textAlign: 'left',
            px: 1,
            py: 0.5,
            border: '1px solid',
            borderColor: 'divider',
            whiteSpace: 'nowrap',
          },
          '& td': {
            px: 1,
            py: 0.5,
            border: '1px solid',
            borderColor: 'divider',
          },
          '& tr:nth-of-type(even)': {
            bgcolor: 'action.hover',
          },
          '& h2, & h3': { mt: 1.5, mb: 0.5, fontSize: '0.95rem' },
          '& hr': { my: 1, borderColor: 'divider' },
          '& details': {
            bgcolor: 'action.selected',
            borderRadius: 1,
            p: 1,
            mb: 1,
            fontSize: '0.8rem',
          },
          '& summary': {
            cursor: 'pointer',
            fontWeight: 600,
            color: 'primary.main',
            fontSize: '0.8rem',
          },
          '& details ul': { my: 0.5, pl: 2 },
          '& details li': { fontSize: '0.75rem', color: 'text.secondary' },
          overflowX: 'auto',
        }}
      >
        {isUser ? (
          <Typography variant="body2">{message.content}</Typography>
        ) : (
          <Typography variant="body2" component="div">
            <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>{message.content}</ReactMarkdown>
          </Typography>
        )}
      </Box>

      {isUser && (
        <PersonIcon
          sx={{ mt: 0.5, fontSize: 20, color: 'text.secondary', flexShrink: 0 }}
        />
      )}
    </Stack>
  );
}


/* ── Loading indicator ───────────────────────────────────────────────────── */

function LoadingIndicator({ toolSteps }: { toolSteps: string[] }) {
  return (
    <Stack spacing={0.5} sx={{ pl: 3.5 }}>
      {toolSteps.length > 0 && (
        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
          {toolSteps.map((step, i) => (
            <Chip key={i} label={step} size="small" variant="outlined" color="primary" />
          ))}
        </Stack>
      )}
      <Stack direction="row" spacing={1} alignItems="center">
        <CircularProgress size={16} />
        <Typography variant="body2" color="text.secondary">
          El asistente está pensando…
        </Typography>
      </Stack>
    </Stack>
  );
}

/* ── Connection banner ───────────────────────────────────────────────────── */

function ConnectionBanner({ onRetry }: { onRetry: () => void }) {
  return (
    <Stack
      direction="row"
      spacing={1}
      alignItems="center"
      justifyContent="center"
      sx={{ py: 1, px: 2, bgcolor: 'warning.light', borderRadius: 1 }}
    >
      <Typography variant="body2" color="warning.contrastText">
        No se pudo conectar con el asistente.
      </Typography>
      <Button
        size="small"
        variant="outlined"
        startIcon={<RefreshIcon />}
        onClick={onRetry}
        sx={{ color: 'warning.contrastText', borderColor: 'warning.contrastText' }}
      >
        Reintentar
      </Button>
    </Stack>
  );
}

/* ── Message list ────────────────────────────────────────────────────────── */

function MessageList({
  messages,
  loading,
  toolSteps,
}: {
  messages: ChatMessage[];
  loading: boolean;
  toolSteps: string[];
}) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  if (messages.length === 0 && !loading) {
    return (
      <Box
        sx={{
          flexGrow: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Stack alignItems="center" spacing={1}>
          <Box
            component="img"
            src={pillAIIcon}
            alt="PharmAssist"
            sx={{ width: 40, height: 40, opacity: 0.4 }}
          />
          <Typography variant="body2" color="text.secondary" textAlign="center">
            Preguntame sobre tus médicos, visitas o ventas
          </Typography>
        </Stack>
      </Box>
    );
  }

  return (
    <Box sx={{ flexGrow: 1, overflow: 'auto', py: 1 }}>
      <Stack spacing={1.5}>
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        {loading && <LoadingIndicator toolSteps={toolSteps} />}
        <div ref={endRef} />
      </Stack>
    </Box>
  );
}

/* ── Message input ───────────────────────────────────────────────────────── */

function MessageInput({
  onSend,
  disabled,
}: {
  onSend: (text: string) => void;
  disabled: boolean;
}) {
  const [text, setText] = useState('');

  const handleSend = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <TextField
      fullWidth
      size="small"
      placeholder="Escribí tu consulta…"
      value={text}
      onChange={(e) => setText(e.target.value)}
      onKeyDown={handleKeyDown}
      disabled={disabled}
      multiline
      maxRows={3}
      slotProps={{
        input: {
          endAdornment: (
            <InputAdornment position="end">
              <IconButton
                onClick={handleSend}
                disabled={disabled || !text.trim()}
                color="primary"
                aria-label="Enviar mensaje"
                edge="end"
              >
                <SendIcon />
              </IconButton>
            </InputAdornment>
          ),
        },
      }}
    />
  );
}

/* ── ChatPanel (main export) ─────────────────────────────────────────────── */

export default function ChatPanel() {
  const messages = useAppStore((s) => s.chatMessages);
  const loading = useAppStore((s) => s.chatLoading);
  const toolSteps = useAppStore((s) => s.toolSteps);
  const wsConnected = useAppStore((s) => s.wsConnected);
  const sendMessage = useAppStore((s) => s.sendMessage);
  const retryWebSocket = useAppStore((s) => s.retryWebSocket);

  return (
    <Card
      sx={{
        flexGrow: 1,
        display: 'flex',
        flexDirection: 'column',
        minHeight: 300,
        height: '100%',
      }}
    >
      <CardContent
        sx={{
          flexGrow: 1,
          display: 'flex',
          flexDirection: 'column',
          gap: 1,
          p: 2,
          '&:last-child': { pb: 2 },
        }}
      >
        {!wsConnected && <ConnectionBanner onRetry={retryWebSocket} />}
        <MessageList messages={messages} loading={loading} toolSteps={toolSteps} />
        <MessageInput onSend={sendMessage} disabled={loading} />
      </CardContent>
    </Card>
  );
}
