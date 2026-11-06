# IABuddy

## TODO.md

[TODO.md](TODO.md) es el estado vivo del proyecto. Actualízalo en el mismo commit que cada avance:

- Marca lo terminado, y añade las decisiones, los errores nuevos y lo que quede por probar.
- Poda al mismo tiempo: condensa o borra lo que ya no ayude a decidir qué sigue. El detalle queda en git, y los resultados de medición que sigan importando van a `docs/`.

Terminado significa que TODO.md refleja el trabajo hecho, tiene la fecha de hoy en la cabecera y ninguna línea describe algo que ya cambió.

## Tests

Verifica cada test con red/green, para comprobar que de verdad prueba el código del proyecto:

- **Red:** velo fallar por la razón esperada, escribiéndolo antes que el código o rompiendo temporalmente el código que cubre.
- **Green:** velo pasar con el código correcto, ya sin ningún cambio temporal.

Un test está verificado solo cuando has visto ambos estados. Si no se pone en rojo al romper el código, corrige el test.
