"""Erros de regra de negócio. Viram HTTP 422 com Problem Details."""


class DomainError(ValueError):
    """Entrada válida no formato, mas que viola uma regra de negócio ou de segurança."""


class ConflictError(DomainError):
    """Estado mudou desde a leitura (versão base divergente, prévia já usada, corrida). HTTP 409."""
