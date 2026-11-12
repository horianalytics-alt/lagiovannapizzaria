# La Giovanna — cardápio digital e gestão da pizzaria

Sistema web para a Pizzaria e Cafeteria La Giovanna: o cliente pede pelo QR Code da mesa, o pedido cai na
tela da cozinha em tempo real, o garçom acompanha o salão pelo celular e a gerência fecha as contas e vê os
números do dia.

## Como rodar

Precisa de Python 3.10 ou mais novo.

```bash
python -m venv .venv
```

No Windows:

```bash
.venv\Scripts\activate
```

No Linux ou macOS:

```bash
source .venv/bin/activate
```

Depois:

```bash
pip install -r requirements.txt
```

```bash
python app.py
```

Abra <http://localhost:5000>. Na primeira vez o sistema cria o banco em `dados/lagiovanna.db` com o cardápio,
12 mesas, a equipe de teste e um movimento fictício para o painel já abrir com números.

- Outra porta: `python app.py --porta 8080`
- Zerar tudo e recriar a demonstração: `python app.py --reiniciar-demo`

### Usar com os celulares na pizzaria

O computador que roda o sistema e os celulares precisam estar na mesma rede Wi-Fi. Ao iniciar, o terminal
mostra o endereço da rede (algo como `http://192.168.0.10:5000`). Entre como gerente, abra
**Mesas e QR Codes**, salve esse endereço e imprima os QR Codes: cada um leva direto para `/mesa/05`, por exemplo.

## Colocar no ar na Vercel

Na Vercel o sistema usa um banco Postgres na nuvem (o disco de lá não guarda arquivos). Fotos do cardápio
também ficam no banco, então não é preciso configurar mais nada.

1. Em <https://vercel.com/new>, importe o repositório. A Vercel reconhece o projeto como **Flask**; deixe
   as opções como estão e clique em **Deploy**. Este primeiro deploy ainda não tem banco e vai mostrar erro
   ao abrir: é esperado.
2. No projeto, abra **Storage → Create Database → Neon (Postgres)**. Escolha a região **Washington, D.C.
   (iad1)**, a mesma em que o código roda por padrão, e conecte o banco ao projeto. A Vercel cria sozinha a
   variável `DATABASE_URL`.
3. Em **Deployments**, abra o último deploy e escolha **Redeploy** para ele enxergar o banco.
4. Abra o endereço do projeto. Na primeira visita o sistema cria as tabelas, o cardápio, as mesas e os
   acessos de teste abaixo.
5. Entre como gerente, confira **Mesas e QR Codes** (os links já saem com o endereço público) e imprima.
   Quando for começar de verdade, use **Zerar as vendas** no fim da tela Resumo e troque as senhas em **Equipe**.

Variáveis opcionais: `SECRET_KEY` (chave das sessões; sem ela, uma é gerada e guardada no banco) e
`FUSO_HORARIO` (padrão `America/Sao_Paulo`).

O plano gratuito (Hobby) da Vercel é para uso pessoal e tem limites mensais de uso. Para a operação
diária da pizzaria, confira os limites e os termos do plano.

## Acessos iniciais

| Perfil  | Usuário   | Senha provisória | Tela       |
|---------|-----------|------------------|------------|
| Gerente | `admin`   | `giovanna123`    | `/admin`   |
| Garçom  | `garcom`  | `garcom123`      | `/garcom`  |
| Cozinha | `cozinha` | `cozinha123`     | `/cozinha` |

Essas senhas são públicas, por isso são provisórias: no primeiro acesso o sistema obriga cada pessoa a criar
a própria senha (8 caracteres ou mais) antes de qualquer outra coisa. **Em um site publicado, entre com os
três usuários logo após o primeiro deploy**, ou alguém de fora pode fazer isso antes. O cliente não tem login:
abre `/mesa/<número>` pelo QR Code.

## O que cada perfil faz

- **Cliente** (`/mesa/05`): cardápio por categoria, pizza inteira ou meio a meio (vale o preço do sabor mais
  caro), borda recheada, observações, envio para a cozinha, acompanhamento do pedido, chamar o garçom e pedir a conta.
- **Garçom**: mapa das mesas (livres, ocupadas, aguardando atendimento), aviso de pedido pronto, lançamento
  de pedidos pelo cliente e confirmação de entrega.
- **Cozinha**: fila em três colunas (pendentes, em preparo, prontos) por ordem de chegada, com a mesa em
  destaque, tempo de espera e aviso sonoro opcional.
- **Gerente**: resumo do dia (faturamento, ticket médio, pedidos, pizzas mais vendidas), caixa (consumo por
  mesa, estorno de item, desconto, taxa de serviço, formas de pagamento, fechamento), cardápio (produtos,
  categorias, bordas, fotos, pausar), mesas com QR Codes e equipe.

## Como é feito

- **Servidor**: Python e Flask. No computador usa SQLite (arquivo em `dados/`) e o Waitress; com a variável
  `DATABASE_URL` definida, usa Postgres. O mesmo código roda nos dois.
- **Atualização das telas**: o servidor guarda um contador por assunto (pedidos, mesas, cardápio, caixa).
  As telas consultam `/api/versao` a cada 3 ou 4 segundos e recarregam só o que mudou. Essa resposta pode
  ser guardada pela CDN por 2 segundos, então muitas telas abertas custam poucas consultas ao banco.
- **Horário**: tudo é registrado no horário de Brasília, mesmo com o servidor em outro fuso.
- **Telas**: Preact + htm, sem etapa de build. Os arquivos ficam em `public/static/`.
- **Segurança**: senhas com hash, sessão por cookie, permissões por perfil conferidas no servidor e preços
  sempre calculados no servidor.

```
app.py              inicia o servidor (e expõe `app` para a Vercel)
lagiovanna/         servidor: banco (db), regras (servicos), rotas, admin, auth, eventos, seed
templates/          páginas HTML
public/static/      CSS, JavaScript, fontes e fotos
tests/              testes automáticos da API
```

## Segurança e LGPD

O que o sistema faz:

- **Senhas**: guardadas com hash (scrypt); senha provisória obriga a troca no primeiro acesso; ao trocar a
  senha, as sessões antigas caem; 8 tentativas erradas bloqueiam o usuário por 15 minutos (contagem no banco).
- **Sessão**: cookie `HttpOnly`, `Secure` e `SameSite=Lax`, com validade de 16 horas; alterações vindas de
  outro site são recusadas.
- **Permissões**: cada rota confere o perfil no servidor; preços e totais são calculados no servidor.
- **Navegador**: Content-Security-Policy sem scripts embutidos, `Referrer-Policy`, `X-Frame-Options`,
  `nosniff`; nenhum recurso de terceiros (fontes e scripts são do próprio site).
- **Rotas abertas** (pedido pelo QR Code): limite de 10 pedidos por mesa a cada 10 minutos e de itens por pedido.
- **Dados pessoais**: o cliente não informa nome, telefone, e-mail nem CPF; não há cookies de rastreamento;
  observações dos pedidos são apagadas 30 dias após o fechamento da conta; excluir alguém da equipe apaga
  nome e usuário; o aviso de privacidade fica em `/privacidade`, com os dados da empresa preenchidos pelo
  gerente em **Privacidade**.

O que depende de quem opera (o sistema não resolve sozinho):

- Preencher razão social, CNPJ e contato em **Privacidade** e revisar o texto do aviso com um advogado ou contador.
- Informar a equipe sobre o tratamento dos dados dela e não compartilhar senhas entre pessoas.
- Vercel e Neon são operadores dos dados; com servidores fora do Brasil há transferência internacional
  (o aviso já informa). Criar o banco na região São Paulo reduz essa exposição.
- Em caso de incidente com dados pessoais, a LGPD exige avaliar e comunicar à ANPD e aos titulares.
- Qualquer pessoa com o endereço consegue abrir `/mesa/<número>` e pedir. O limite por mesa contém abusos,
  mas não impede um pedido falso isolado; a equipe deve conferir pedidos estranhos.

Testes:

```bash
pip install pytest
```

```bash
python -m pytest
```

Para rodar os mesmos testes num Postgres (o banco indicado é apagado), defina `TESTE_POSTGRES_URL`.
