# Dashboard de gestão do SAC

Painel Streamlit para o fechamento mensal dos relatórios do Zendesk. Ele consolida volume, eficiência, equipe, backlog, satisfação e SLA, com alertas de cobertura para evitar conclusões baseadas em amostras pequenas.

## Estrutura do repositório

```text
app.py
requirements.txt
Zendesk-Support_Tickets_*.xlsx
Zendesk-Support_Efficiency_*.xlsx
Zendesk-Support_Assignee-activity_*.xlsx
Zendesk-Support_Agent-updates_*.xlsx
Zendesk-Support_Unsolved-tickets_*.xlsx
Zendesk-Support_Backlog_*.xlsx
Zendesk-Support_SLAs_*.xlsx
Zendesk-Support_Satisfaction_*.xlsx
```

Há ainda uma nona fonte recomendada, a base `export-*.csv.zip`. **Não envie essa ZIP ao GitHub**, pois ela contém dados pessoais de clientes. Carregue-a pela barra lateral do painel quando for fazer a análise. O código lê somente campos operacionais seguros e ignora e-mail, CPF/CNPJ, telefone, assunto e descrição.

O app usa o arquivo mais recente de cada prefixo. Para atualizar o mês, apague as oito planilhas antigas, envie as novas e faça um commit. O Streamlit Community Cloud refaz o deploy automaticamente após a alteração no GitHub.

## Testar no computador

No PowerShell, dentro desta pasta:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

Se preferir, rode o app sem copiar nenhuma base e carregue os oito relatórios e a ZIP detalhada pela barra lateral.

## Criar o novo dashboard no GitHub

### Caminho mais simples, pelo navegador

1. Acesse `github.com/new`.
2. Crie um repositório, por exemplo `dashboard-sac`. A opção mais segura é subir somente o código; se quiser guardar relatórios internos no repositório, ele e o app devem ser privados.
3. No repositório, escolha **Add file → Upload files**.
4. Arraste `app.py`, `requirements.txt`, `.gitignore` e `README.md`. Se o repositório e o app forem privados, você pode incluir as oito planilhas `.xlsx`. Não envie a base detalhada `.csv.zip`.
5. Confirme em **Commit changes**.

### Alternativa pelo terminal

Depois de criar um repositório vazio no GitHub:

```powershell
git init
git add app.py requirements.txt README.md
git commit -m "Cria dashboard mensal do SAC"
git branch -M main
git remote add origin https://github.com/SEU-USUARIO/dashboard-sac.git
git push -u origin main
```

## Publicar no Streamlit Community Cloud

1. Acesse `share.streamlit.io` e conecte sua conta do GitHub.
2. Clique em **Create app** e depois **Yup, I have an app**.
3. Selecione o repositório `dashboard-sac`, branch `main` e arquivo `app.py`.
4. Escolha o endereço desejado e clique em **Deploy**.

O painel não exige secrets nem banco de dados. Repositórios privados funcionam desde que o Streamlit tenha acesso autorizado ao repositório.

## Rotina mensal

1. Exporte os mesmos oito relatórios e a base detalhada no Zendesk para o mês fechado.
2. Confira se os nomes continuam começando pelos prefixos listados acima.
3. Exclua os relatórios antigos no GitHub e envie os novos, se o ambiente for privado. Nunca envie a ZIP detalhada ao GitHub.
4. Faça o commit e aguarde o redeploy.
5. Abra o painel, carregue a ZIP detalhada na barra lateral e confira a aba **Qualidade dos dados**, especialmente a cobertura da base, do SLA e do CSAT.

## Observação importante

Os oito relatórios são agregados e definem os números oficiais do fechamento. A ZIP acrescenta investigação ticket a ticket, motivos e cruzamentos operacionais. Como a cobertura da ZIP pode ser menor que os totais oficiais, o painel mostra a reconciliação na aba **Qualidade dos dados** e nunca substitui silenciosamente um total pelo outro.

## Referências oficiais

- [Criar e enviar um projeto ao GitHub](https://docs.github.com/en/get-started/start-your-journey/uploading-a-project-to-github)
- [Publicar um app no Streamlit Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)
