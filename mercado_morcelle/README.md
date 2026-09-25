# Mercado Morcelle — Sistema Web

Sistema web completo do Mercado Morcelle: um "jornal digital de ofertas" público, com painel administrativo protegido para gerenciar produtos, categorias, promoções e imagens.

**Tecnologias:** Python + Flask + Jinja2 + SQLite + HTML5 + CSS3 + JavaScript puro.

---

## 1. Instalar o Python

Baixe e instale o Python 3.10 ou superior em https://www.python.org/downloads/
(no instalador do Windows, marque a opção **"Add Python to PATH"**).

Verifique a instalação no terminal:

```
python --version
```

## 2. Abrir o projeto

Extraia a pasta `mercado_morcelle` em um local de sua preferência e abra um terminal dentro dela.

## 3. Criar o ambiente virtual

```
python -m venv venv
```

## 4. Ativar o ambiente virtual

**Windows:**
```
venv\Scripts\activate
```

**Linux / macOS:**
```
source venv/bin/activate
```

## 5. Instalar as dependências

```
pip install -r requirements.txt
```

## 6. Executar o sistema

```
python app.py
```

Na primeira execução, o sistema cria automaticamente:
- o arquivo `database.db`
- todas as tabelas
- as categorias padrão (Mercearia, Hortifruti, Açougue, Frios, Laticínios, Higiene, Limpeza, Bebidas, Padaria, Outros)
- o usuário administrador inicial

## 7. Abrir no navegador

**Site público (jornal de ofertas):**
```
http://127.0.0.1:5000
```

**Painel administrativo:**
```
http://127.0.0.1:5000/login
```

---

## Usuário administrador inicial

```
E-mail: admin@mercadomorcelle.com
Senha:  MudeEssaSenha123!
```

### ⚠️ Como trocar a senha

1. Faça login com os dados acima.
2. No menu lateral, clique em **Configurações**.
3. Informe a senha atual e a nova senha (mínimo 8 caracteres).
4. Clique em **Alterar senha**.

**Troque essa senha assim que possível — ela não deve ser usada em produção.**

---

## Como usar o sistema

### Cadastrar um produto

1. Faça login em `/login`.
2. No menu, clique em **Adicionar produto**.
3. Preencha nome, descrição, categoria e preço.
4. Em **Imagens**, clique em **ESCOLHER IMAGENS** e selecione uma ou mais fotos do seu computador, celular ou tablet (funciona com a galeria, o app Arquivos ou a câmera, quando o navegador oferecer essa opção).
5. Confira a prévia das imagens e clique em **CADASTRAR PRODUTO**.

A primeira imagem enviada é marcada automaticamente como **imagem principal** (a que aparece nos cards do site).

### Onde ficam as imagens

Todas as imagens enviadas são salvas fisicamente em:

```
static/uploads/produtos/
```

com nomes únicos gerados automaticamente (ex: `produto_a83f9212.jpg`), evitando que um arquivo substitua o outro por engano. O caminho de cada imagem também fica registrado no banco de dados (tabela `imagens_produto`).

### Trocar ou adicionar imagens de um produto já cadastrado

1. Vá em **Produtos** → **Editar** no produto desejado.
2. Você verá as imagens atuais. É possível:
   - Marcar outra imagem como **principal** (ícone ★).
   - Excluir uma imagem secundária (ícone ✕).
   - Adicionar novas imagens pelo mesmo botão **ESCOLHER IMAGENS**.
3. Clique em **SALVAR ALTERAÇÕES**.

### Criar uma promoção

1. No menu, clique em **Promoções** → **Nova promoção**.
2. Escolha o produto, o preço promocional e o período (data inicial e data final).
3. O sistema não permite cadastrar um preço promocional maior ou igual ao preço normal.
4. A promoção só aparece como "OFERTA" no site público **dentro do período informado** — isso é verificado automaticamente pela data atual, sem depender de você desativá-la manualmente depois que ela vence.

### Como alterar a logo

A logo oficial já está aplicada no sistema em:

```
static/images/logo.png
```

Para trocar por uma nova versão, basta substituir esse arquivo por outro **com o mesmo nome** (`logo.png`). Ela é usada automaticamente no cabeçalho do site, na página inicial, no login e no painel administrativo.

---

## Estrutura de pastas

```
mercado_morcelle/
├── app.py                     → aplicação Flask (rotas, banco, autenticação, upload)
├── database.db                → banco SQLite (criado automaticamente)
├── requirements.txt
├── README.md
│
├── templates/
│   ├── base.html               → layout do site público
│   ├── index.html               → jornal digital de ofertas (página inicial)
│   ├── _product_card.html       → card de produto reutilizável
│   ├── produto_detalhes.html
│   ├── login.html
│   ├── 404.html
│   └── admin/
│       ├── _admin_base.html    → layout do painel (sidebar + topbar)
│       ├── dashboard.html
│       ├── produtos.html
│       ├── produto_form.html
│       ├── categorias.html
│       ├── promocoes.html
│       ├── promocao_form.html
│       ├── logs.html
│       └── configuracoes.html
│
├── static/
│   ├── css/style.css
│   ├── js/script.js
│   ├── images/logo.png
│   ├── uploads/produtos/       → imagens enviadas pelo admin
│   ├── manifest.json           → PWA
│   └── service-worker.js       → PWA
```

---

## Segurança

- Senhas nunca são salvas em texto puro — são protegidas com `generate_password_hash` / `check_password_hash` (Werkzeug).
- Todas as rotas `/admin/*` exigem login. A verificação acontece no backend (decorator `@login_required`), não apenas no frontend — mesmo que alguém tente acessar a URL diretamente sem estar logado, é redirecionado para `/login`.
- Uploads usam `secure_filename`, geram nomes únicos com UUID, validam extensão (jpg, jpeg, png, webp) e limitam o tamanho a 5 MB.
- Chave de sessão configurável via variável de ambiente `SECRET_KEY`.

## Fora do escopo (intencionalmente)

Este sistema é apenas para divulgação de produtos e promoções. Ele **não** inclui carrinho, checkout, pagamento (PIX/cartão), venda online, nota fiscal, sistema fiscal/ERP ou programa de fidelidade.

## Banco de dados

Usa SQLite (`database.db`) com chaves estrangeiras habilitadas. O código foi organizado com funções de acesso ao banco isoladas, o que facilita uma futura migração para PostgreSQL ou MySQL, caso necessário.
