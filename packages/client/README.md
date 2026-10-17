# Client communication

Shared HTTP/WS clients, event decoding, reconnect handling and device cursor persistence belong here. UI state and visual components belong to apps and `packages/ui`.

The app supplies service endpoints, user authentication and platform storage. A replay cursor advances after the consumer durably handles an event; transports must not acknowledge data solely because a frame arrived. Closing a socket must not implicitly send task cancellation.
