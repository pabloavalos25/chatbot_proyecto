# Chatbot de servicios — MVP local

Al terminar una atención, el operador autorizado solicita el cierre desde el panel. La conversación queda pendiente de encuesta; el cliente puede calificar de 1 (muy satisfecho) a 5 (nada satisfecho) y agregar un comentario opcional. Al enviar la encuesta se cierra la conversación y se conserva el historial. Un cliente no puede iniciar el cierre por su cuenta. La solicitud queda pendiente si el cliente recarga la página.

API local para un chatbot de negocios de servicios, con catálogo ficticio de estacionamiento. Usa reglas locales por defecto y admite una integración opcional con OpenAI. No conecta WhatsApp ni sistemas de estacionamiento. Los servicios son ilustrativos: no se proporcionan precios ni disponibilidad confirmados.

Datos de ejemplo para las pruebas: todos los días de 07:00 a 23:00; vehículos admitidos: autos, camionetas y camiones; medios de pago: efectivo, Mercado Pago, tarjetas de crédito y débito Visa o Mastercard, y QR. El QR se genera al confirmar la reserva o el abono; este prototipo no lo genera. Nombre, dirección, precios y disponibilidad siguen sin confirmar.

Al pedir una reserva, el bot solicita nombre, vehículo, color, patente, fecha y horario aproximado de entrada y salida. La solicitud queda registrada para revisión; no es una reserva confirmada ni garantiza disponibilidad. Se puede cancelar la carga escribiendo «cancelar reserva» o pedir atención humana. La fecha se solicita como DD/MM/AAAA y las horas en formato de 24 horas; si la salida es igual o anterior a la entrada, se pregunta si corresponde al día siguiente.

## Requisitos e instalación

Python 3.10 o superior. En PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

En Linux/macOS: `python3 -m venv .venv` y `source .venv/bin/activate`. Si fuera necesario, crear un archivo local `.env` para configurar `DATABASE_URL` y las demás variables. No subir `.env` al repositorio.

## Ejecución y pruebas

```powershell
uvicorn app.main:app --reload
python -m pytest -q
```

La aplicación crea las tablas al iniciar y utiliza `chatbot.db` por defecto. Abrí http://127.0.0.1:8000/ para usar la interfaz de pruebas y http://127.0.0.1:8000/docs para la documentación interactiva. En la interfaz, enviá un mensaje como cliente, pedí hablar con una persona y seleccioná la conversación en el panel de atención humana para responder o devolverla al bot.

## IA opcional para pruebas

Por defecto la IA está desactivada. Para probarla, editá tu copia local de `.env`, colocá allí tu clave de API y configurá:

```text
CHATBOT_AI_ENABLED=true
OPENAI_API_KEY=tu_clave_aqui
OPENAI_MODEL=gpt-4.1-mini
```

Reiniciá el servidor para aplicar los cambios. No compartas ni subas `.env` ni la clave; el uso de la API puede generar cargos. Si falta la clave, la IA está desactivada o el proveedor falla, se usan las reglas locales. La conexión configura tiempos de espera de ocho segundos por operación de red; esto no garantiza un límite total de ocho segundos para toda la solicitud. La derivación a una persona y las solicitudes comerciales reconocidas por las reglas permanecen bajo control local, aunque las reglas no reconocen todas las formas de expresarlas.

La solicitud a OpenAI contiene el texto actual del cliente, que podría incluir datos personales; no se envían el identificador del cliente ni el historial por separado. Se usa `store=false`, que no implica que no exista ninguna retención o registro por parte del proveedor. El modelo no recibe el historial, por lo que no recuerda preguntas anteriores. El catálogo y los datos del negocio son ilustrativos: una respuesta generada puede equivocarse o inventar información pese a las instrucciones. Revisá los resultados y definí los datos reales antes de utilizarlo con clientes. Esta integración aún no fue probada con una clave real.

## IA local opcional con Ollama

Como alternativa a OpenAI, se puede ejecutar un modelo en esta computadora con Ollama, sin cargos por API. Instalá Ollama desde https://ollama.com/download y descargá un modelo pequeño con `ollama pull qwen2.5:1.5b`. La descarga requiere Internet y espacio en disco. El modelo se ejecuta en la computadora y puede tardar, especialmente con 8 GB de memoria; su calidad y velocidad deben evaluarse en esta máquina. Consultá la licencia del modelo antes de usarlo comercialmente.

Con Ollama en ejecución, agregá o editá estas líneas en tu `.env` y reiniciá el servidor:

```text
CHATBOT_AI_ENABLED=true
CHATBOT_AI_PROVIDER=ollama
OLLAMA_MODEL=qwen2.5:1.5b
```

El adaptador se conecta solamente a `127.0.0.1:11434` y no utiliza ni envía la clave de OpenAI. Si Ollama no está activo, el modelo no está descargado o falla la respuesta, se utilizan las reglas locales. La conexión usa un límite de dos segundos para conectar y 120 segundos de inactividad de lectura, no un plazo total garantizado. El modelo recibe el mensaje actual, no el historial; puede inventar información y no debe usarse con clientes reales sin evaluar sus respuestas y confirmar los datos del negocio. Las reglas reconocen algunas, pero no todas, las formas de pedir atención humana. La llamada al modelo se hace con una transacción de SQLite abierta, por lo que puede demorar otras escrituras.

Para volver a OpenAI, configurá `CHATBOT_AI_PROVIDER=openai` con la clave y facturación correspondientes. Para desactivar toda IA, usá `CHATBOT_AI_ENABLED=false`.

## API

- `GET /health` devuelve `{"status":"ok"}`; indica que el proceso responde, no verifica dependencias.
- `POST /api/chat` recibe `{"customer_id":"cliente-123","message":"Hola"}` y devuelve `conversation_id`, `state`, `response` e `intent`.

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/chat -ContentType 'application/json' -Body '{"customer_id":"cliente-123","message":"Hola"}'
```

Cada navegador recibe una cookie aleatoria para identificar su conversación; `customer_id` se conserva por compatibilidad pero se ignora. Borrar la cookie inicia una conversación nueva, y las conversaciones antiguas basadas en identificadores elegidos no se asocian automáticamente. `GET /api/chat/messages` devuelve el estado y el historial propios de la cookie. Cuando solicita una persona, recibe un aviso de derivación y la conversación pasa a `HUMAN`. Los mensajes posteriores se guardan y devuelven `response: null` e `intent: null`, sin respuesta automática. Las solicitudes comerciales se guardan sin efectuar reservas ni prometer disponibilidad. Los mensajes y solicitudes se almacenan en texto plano en la base local.

### Atención humana local

- `GET /api/conversations?state=HUMAN`: lista conversaciones; el filtro es opcional.
- `GET /api/conversations/{id}/messages`: consulta el historial.
- `POST /api/conversations/{id}/messages`: registra una respuesta del operador con `{"message":"Hola"}`; requiere estado `HUMAN`.
- `PATCH /api/conversations/{id}/state`: cambia el estado con `{"state":"BOT"}` o `{"state":"HUMAN"}`.

Los endpoints de operador requieren `Authorization: Bearer <token>`. Para habilitarlos definí en `.env` un `OPERATOR_TOKEN` privado de al menos 32 caracteres aleatorios y reiniciá el servidor. Ingresá ese mismo token en el panel de operador; no lo compartas ni lo incluyas en el código. Sin token configurado el acceso se rechaza. Las respuestas de operador se registran localmente; no se envían a WhatsApp. Esta protección es para pruebas locales: no exponer el servidor a Internet ni redes compartidas; aún faltan HTTPS, una solución de identidad para producción, límites de acceso y políticas de retención.

Para generar el token en la computadora sin mostrarlo en la consola, con el entorno virtual activo y desde la carpeta del proyecto, ejecutá:

```powershell
python -c "from pathlib import Path; import secrets; p=Path('.env'); s=p.read_text(encoding='utf-8'); assert not any(line.strip().startswith('OPERATOR_TOKEN=') for line in s.splitlines()), 'Ya existe OPERATOR_TOKEN; no se modificó'; p.write_text(s.rstrip() + '\nOPERATOR_TOKEN=' + secrets.token_urlsafe(32) + '\n', encoding='utf-8')"
```

El comando requiere un `.env` existente y se detiene sin modificarlo si ya contiene `OPERATOR_TOKEN`. Abrí `.env` en un editor local para ingresar el valor en el panel, sin compartirlo. Reiniciá el servidor para aplicar cambios. Borrar la cookie o usar otro navegador crea una identidad distinta; esto no autentica personas y no reemplaza la identidad de un canal futuro como WhatsApp.

## Estructura

```text
app/
  domain/          catálogo y reglas conversacionales
  integrations/    contratos para canales y sistema de estacionamiento
  config.py        configuración de entorno
  database.py      conexión y sesiones
  models.py        modelos de persistencia
  schemas.py       contratos HTTP
  service.py       coordinación de la conversación
  main.py          endpoints y arranque
tests/             pruebas HTTP y persistencia
requirements.txt   dependencias
```

Los protocolos en `integrations/ports.py` son puntos de extensión para canales y sistemas de estacionamiento. Para adaptar el MVP a otro negocio, sustituir el catálogo y las reglas; para producción se necesitarán, entre otras cosas, migraciones y control de acceso.

El motor utiliza reglas locales y respuestas predefinidas: reconoce consultas habituales del estacionamiento y reconduce mensajes que no entiende. La detección por palabras no comprende todos los matices y no garantiza bloquear toda consulta ajena al negocio; puede equivocarse con mensajes ambiguos o temas mezclados. No ejecuta instrucciones incluidas en los mensajes.
