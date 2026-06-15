-- 002_owners_accounts.sql
-- Multi-tenancy root tables. Every domain table references owner_id.

CREATE TABLE owners (
    id           SERIAL       PRIMARY KEY,
    email        TEXT         NOT NULL UNIQUE,
    display_name TEXT         NOT NULL,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE accounts (
    id              SERIAL      PRIMARY KEY,
    owner_id        INT         NOT NULL REFERENCES owners(id),
    ibkr_account_id TEXT        NOT NULL UNIQUE,  -- e.g. U15760849
    label           TEXT        NOT NULL,           -- "Trading", "Long-term"
    role            TEXT        NOT NULL,           -- "aggressive-options", "buy-hold", "etf"
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX accounts_owner_idx ON accounts (owner_id);

-- Seed the single current owner and trading account.
-- Password/auth is Metabase's concern; this just anchors the data model.
INSERT INTO owners (email, display_name)
VALUES ('investforecom@gmail.com', 'Char');

INSERT INTO accounts (owner_id, ibkr_account_id, label, role)
VALUES (
    (SELECT id FROM owners WHERE email = 'investforecom@gmail.com'),
    'U15760849',
    'Trading',
    'aggressive-options'
);
