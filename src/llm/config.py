"""Provider configuration: where to send requests and where to find keys."""

import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from dotenv import dotenv_values
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    TypeAdapter,
    field_validator,
)


class ApiKey(BaseModel):
    """One API key of a provider, read from the environment.

    The secret is wrapped in ``SecretStr`` so that printing, logging or
    dumping the object never reveals it; ``value.get_secret_value()`` is
    called only when building the HTTP request.
    """

    model_config = ConfigDict(frozen=True)

    env_name: str = Field(
        description="Variable the key came from, e.g. 'GROQ_API_KEY_2'; "
        "safe to log"
    )
    value: SecretStr
    account_id: str | None = Field(
        default=None,
        description="Account the key belongs to, for providers whose URL "
        "contains '{account_id}' (Cloudflare)",
    )


class ProviderConfig(BaseModel):
    """Static description of one OpenAI-compatible LLM provider.

    Holds no secret: API keys are read from environment variables whose
    names start with ``key_env_prefix`` (``<PREFIX>_API_KEY``,
    ``<PREFIX>_API_KEY_2``, ...).
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, description="Short id, e.g. 'openrouter'")
    base_url: str = Field(
        pattern=r"^https?://",
        description="API root, e.g. 'https://openrouter.ai/api/v1'",
    )
    key_env_prefix: str = Field(
        pattern=r"^[A-Z][A-Z0-9_]*$",
        description="Env var prefix of the keys, e.g. 'OPENROUTER'",
    )

    @field_validator("base_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        """Normalise the URL so that '/chat/completions' can be appended."""
        return value.rstrip("/")

    def matches_url(self, url: str) -> bool:
        """Tell whether ``url`` is this provider's API root.

        A trailing slash is ignored. In ``base_url``, the
        ``{account_id}`` placeholder stands for any single path segment,
        so the real Cloudflare URL of any account matches.
        """
        pattern = re.escape(self.base_url).replace(
            re.escape("{account_id}"), "[^/]+"
        )
        return re.fullmatch(pattern, url.rstrip("/")) is not None

    def load_keys(
        self,
        environ: Mapping[str, str] | None = None,
        env_file: Path = Path(".env"),
    ) -> list[ApiKey]:
        """Collect this provider's API keys from the environment, in order.

        Reads ``<PREFIX>_API_KEY`` then ``<PREFIX>_API_KEY_2``, ``_3``, ...
        (gaps in the numbering are allowed). Empty values are ignored, so
        an unfilled ``.env`` simply yields no key. When the URL contains
        ``{account_id}``, each key requires the matching
        ``<PREFIX>_ACCOUNT_ID`` (same suffix).

        Args:
            environ: variables to read. By default, the process
                environment completed by ``env_file``; variables already
                set in the process win over the file.
            env_file: dotenv file read when ``environ`` is not given; a
                missing file is not an error.

        Returns:
            The keys sorted by number; an empty list if none is set.

        Raises:
            ValueError: a key needs an account id that is missing.
        """
        if environ is None:
            from_file = {
                name: value
                for name, value in dotenv_values(env_file).items()
                if value is not None
            }
            env: Mapping[str, str] = {**from_file, **os.environ}
        else:
            env = environ
        key_var = f"{self.key_env_prefix}_API_KEY"
        pattern = re.compile(rf"^{re.escape(key_var)}(?:_(\d+))?$")
        needs_account = "{account_id}" in self.base_url

        numbered: list[tuple[int, ApiKey]] = []
        for name, value in env.items():
            match = pattern.match(name)
            if match is None or not value.strip():
                continue
            suffix = name[len(key_var):]  # "" for the first key, "_2" etc.
            account_id: str | None = None
            if needs_account:
                account_var = f"{self.key_env_prefix}_ACCOUNT_ID{suffix}"
                account_id = env.get(account_var, "").strip()
                if not account_id:
                    raise ValueError(
                        f"{name} is set but {account_var} is not"
                    )
            key = ApiKey(
                env_name=name,
                value=SecretStr(value.strip()),
                account_id=account_id,
            )
            numbered.append((int(match.group(1) or 1), key))

        numbered.sort(key=lambda item: item[0])
        return [key for _, key in numbered]


class ProviderRegistry:
    """The set of known providers, indexed by name."""

    def __init__(self, providers: Sequence[ProviderConfig]) -> None:
        """Index ``providers`` by name.

        URLs are checked here, once, so that a bad providers file fails at
        load time rather than when an agent looks a URL up. Two URLs
        overlap when one matches the other (see ``matches_url``), which
        also catches a hard-coded Cloudflare URL next to the template.

        Raises:
            ValueError: two providers share the same name or have
                overlapping URLs.
        """
        self._by_name: dict[str, ProviderConfig] = {}
        for provider in providers:
            if provider.name in self._by_name:
                raise ValueError(
                    f"duplicate provider name: {provider.name!r}"
                )
            for known in self._by_name.values():
                if provider.matches_url(known.base_url) or known.matches_url(
                    provider.base_url
                ):
                    raise ValueError(
                        f"providers {known.name!r} and {provider.name!r} "
                        f"have overlapping URLs: {known.base_url!r}, "
                        f"{provider.base_url!r}"
                    )
            self._by_name[provider.name] = provider

    @classmethod
    def from_file(cls, path: Path) -> "ProviderRegistry":
        """Build the registry from a JSON list of providers.

        Raises:
            OSError: the file cannot be read.
            pydantic.ValidationError: the JSON is malformed or a provider
                is invalid.
            ValueError: two providers share the same name or have
                overlapping URLs.
        """
        adapter = TypeAdapter(list[ProviderConfig])
        return cls(adapter.validate_json(path.read_text(encoding="utf-8")))

    def get(self, name: str) -> ProviderConfig:
        """Return the provider called ``name``.

        Raises:
            KeyError: no provider has this name.
        """
        try:
            return self._by_name[name]
        except KeyError:
            known = ", ".join(sorted(self._by_name))
            raise KeyError(
                f"unknown provider {name!r} (known: {known})"
            ) from None

    def find_by_url(self, url: str) -> ProviderConfig:
        """Return the provider whose API root is ``url``.

        Used for the ``--provider-url`` option of the agents; see
        ``ProviderConfig.matches_url`` for how URLs are compared. At most
        one provider can match: ``__init__`` rejects overlapping URLs.

        Raises:
            KeyError: no provider has this URL.
        """
        for provider in self._by_name.values():
            if provider.matches_url(url):
                return provider
        known = ", ".join(
            provider.base_url for provider in self._by_name.values()
        )
        raise KeyError(f"unknown provider URL {url!r} (known: {known})")
