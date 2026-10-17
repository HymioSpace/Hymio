# CLI commands

Add Python modules with Oath `COMMANDS` declarations. Oath's Biz service hosts these handlers, and `oath-cli` invokes them through HTTP. They are distinct from Hymio's product backend and should call its APIs when business services are needed.

Handlers receive runtime user identity and current `user_context`. User-provided context values are input, not verified authorization; business APIs must validate credentials independently.
