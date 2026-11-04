# Publicador multi-red

Conecta tus cuentas una vez y publica el mismo texto, imagen o video **desde tu PC** en Facebook, Instagram, X, LinkedIn y Telegram a la vez.

## Cómo se usa

1. Abre el Publicador (doble clic).
2. En **Mis cuentas**, pulsa **Conectar** en cada red. Se abre tu navegador, inicias sesión con tu usuario y contraseña de siempre y aceptas los permisos. Al volver, la red aparece con ✔ y tu nombre de cuenta.
   - Facebook e Instagram se conectan juntos (Instagram va ligado a tu Página de Facebook).
3. Escribe el texto, pulsa **Elegir imagen o video…** para escoger un archivo de tu PC y, si quieres, añade un enlace.
4. Marca las redes y pulsa **Publicar en todas**. Abajo verás el resultado de cada red.

Las sesiones se guardan en `cuentas.json`, junto al programa, así que no tienes que volver a conectar cada vez. Trata ese archivo como una contraseña.

## Preparación (una sola vez): crear tus "apps" de desarrollador

Las redes solo dejan que un programa publique por ti si ese programa está registrado como app en su portal de desarrolladores. Es gratis, se hace una vez y luego solo usas los botones Conectar. Pulsa **Datos de apps (config.json)** en el programa y pega ahí los datos de cada app.

En todas, la dirección de retorno (redirect / callback URL) es: **`http://localhost:8765/callback`**

| Red | Dónde | Qué configurar | Qué pegar en config.json |
|---|---|---|---|
| **Facebook + Instagram** | developers.facebook.com → Crear app (tipo "Empresa") | Añade "Inicio de sesión con Facebook" y la "API de Instagram". Pon la redirect URL. Debes ser administrador de una **Página**, y tu Instagram debe ser **Profesional** y estar vinculado a ella | `meta.app_id`, `meta.app_secret` |
| **X** | developer.x.com → Proyecto → App → "User authentication settings" | Permisos "Read and write", tipo "Web App", callback URL | `x.client_id`, `x.client_secret` |
| **LinkedIn** | linkedin.com/developers → Create app | Productos "Sign In with LinkedIn using OpenID Connect" y "Share on LinkedIn". Redirect URL en la pestaña Auth | `linkedin.client_id`, `linkedin.client_secret` |
| **Telegram** | Habla con @BotFather → /newbot | Haz al bot administrador de tu canal | `telegram.bot_token`, `telegram.chat_id` (ej. `@micanal`) |

Mientras tu app de Meta esté en "modo desarrollo", solo funciona con tus propias cuentas (las que tienen rol en la app), que es justo lo que necesitas para uso personal.

## Qué publica cada red

| Red | Texto | Imagen | Video | Notas |
|---|---|---|---|---|
| Facebook | ✔ | ✔ | ✔ | Solo en Páginas, no en perfiles personales (norma de Meta) |
| Instagram | — | ✔ | ✔ (como Reel) | Siempre necesita imagen o video |
| X | ✔ (280 car.) | ✔ | ✔ | El plan gratuito de la API permite pocos posts al mes |
| LinkedIn | ✔ | ✔ | ✔ | La sesión caduca a los 60 días: pulsa Reconectar |
| Telegram | ✔ | ✔ | ✔ | Máx. 50 MB por archivo |

Formatos: JPG, PNG, GIF, WEBP, MP4, MOV.

## Crear el programa instalable para Windows

- **Automático (GitHub):** al subir esta carpeta a un repositorio, `.github/workflows/windows.yml` compila `Publicador-Setup.exe` (instala el programa con accesos directos y desinstalador).
- **En tu PC:** instala Python desde python.org (marca "Add python.exe to PATH") y haz doble clic en `crear_exe_windows.bat`.

## Línea de comandos (opcional)

```
python publicar.py --conectar facebook
python publicar.py "Mi post" --archivo C:\fotos\foto.jpg --link https://misitio.com
python publicar.py "Prueba" --redes facebook,x --simular
```

## Pendiente

TikTok y YouTube (requieren auditoría o verificación de la app por parte de cada red), varias imágenes por publicación, programar publicaciones para una fecha y texto distinto por red.
