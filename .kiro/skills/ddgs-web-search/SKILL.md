---
name: ddgs-web-search
description: Referencia de uso de DDGS (metabuscador sin API key) para búsqueda de información pública de médicos en PharmAssist. Usar al implementar o modificar backend/tools/web_search*.py, backend/tools/generacion*.py, o tools de agentcore que buscan info pública.
metadata:
  category: development
  complexity: beginner
---

# DDGS — Web Search para PharmAssist

## Qué es

DDGS (Dux Distributed Global Search) es un metabuscador open source que agrega resultados de múltiples motores (Google, Bing, DuckDuckGo, Brave, Yahoo). Sin API key, sin costo, sin límites duros.

- **Paquete**: `ddgs` (PyPI)
- **Instalación**: `pip install -U ddgs`
- **GitHub**: https://github.com/deedy5/duckduckgo_search
- **Versión probada**: 9.13.0

## Uso básico

```python
from ddgs import DDGS

# Búsqueda de texto (backend auto selecciona el mejor motor)
results = DDGS().text("Dr. Kreutzer cirugía cardiovascular", max_results=5)

# Búsqueda con backend específico de Google (recomendado para médicos)
results = DDGS().text(
    "Dr. Christian Kreutzer Hospital Austral publicaciones",
    region="ar-es",
    max_results=5,
    backend="google"
)

# Cada resultado es un dict:
# {
#     "title": "Kreutzer, Christian - Hospital Universitario Austral",
#     "href": "https://www.hospitalaustral.edu.ar/medicos/christian-kreutzer/",
#     "body": "Médico egresado de la Facultad de Medicina, UBA..."
# }
```

## Parámetros de text()

```python
DDGS().text(
    query: str,              # Texto de búsqueda
    region: str = "us-en",   # Usar "ar-es" para resultados argentinos
    safesearch: str = "moderate",
    timelimit: str | None = None,  # "d" (día), "w" (semana), "m" (mes), "y" (año)
    max_results: int = 10,
    page: int = 1,
    backend: str = "auto",   # "auto", "google", "bing", "duckduckgo", "brave"
) -> list[dict[str, str]]
```

## Extracción de contenido (opcional)

```python
# Extraer contenido de una URL en formato Markdown
content = DDGS().extract("https://example.com", fmt="text_markdown")
# Retorna: {"url": "...", "content": "# Título\n\nContenido..."}

# Formatos disponibles: "text_markdown", "text_plain", "text_rich", "text", "content"
```

## Recomendaciones para PharmAssist

### Para el brief de médico

Los **snippets de búsqueda son suficientes** como input para Claude. No necesitamos `extract()` en la mayoría de los casos — trae mucho boilerplate HTML de navegación. El LLM arma un brief rico con títulos, URLs y snippets de 5 resultados.

```python
@tool
def buscar_info_publica_medico(nombre: str, apellido: str, especialidad: str, hospital: str = "") -> dict:
    """Busca información pública de un médico en internet usando DDGS."""
    try:
        query = f"Dr. {nombre} {apellido} {especialidad}"
        if hospital:
            query += f" {hospital}"
        query += " Argentina"

        results = DDGS().text(query, region="ar-es", max_results=5, backend="google")

        # Retornar snippets — el LLM combina con datos CRM para el brief
        search_data = [
            {
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", "")
            }
            for r in results
        ]

        return {
            "success": True,
            "message": f"✅ Se encontraron {len(results)} resultados para Dr. {nombre} {apellido}",
            "data": search_data
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"⚠️ No se pudo buscar info pública: {str(e)}. El brief se generará solo con datos internos."
        }
```

### Manejo de errores

- DDGS puede fallar si el motor de búsqueda bloquea temporalmente (rate limiting)
- Siempre tener fallback: si falla web search, generar brief solo con datos CRM
- No cachear resultados para la demo (datos frescos)
- Timeout default es 5 segundos — suficiente para la demo

### Backends disponibles

| Backend | Calidad | Velocidad | Estabilidad |
|---------|---------|-----------|-------------|
| `"google"` | Excelente | ~1-2s | Buena (puede rate-limit) |
| `"bing"` | Buena | ~1s | Buena |
| `"duckduckgo"` | Buena | ~1s | Alta |
| `"brave"` | Buena | ~1s | Alta |
| `"auto"` | Variable | ~1-2s | Alta (fallback automático) |

**Recomendación**: usar `backend="google"` como primera opción, con fallback a `"auto"` si falla.

### No usar extract() salvo que sea necesario

El `extract()` convierte HTML a Markdown pero trae mucho ruido (menús, footers, navegación). Solo usarlo si necesitás contenido detallado de una URL específica y el snippet no alcanza.
