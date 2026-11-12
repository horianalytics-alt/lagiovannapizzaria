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

## Acessos de teste

| Perfil  | Usuário   | Senha         | Tela       |
|---------|-----------|---------------|------------|
| Gerente | `admin`   | `giovanna123` | `/admin`   |
| Garçom  | `garcom`  | `garcom123`   | `/garcom`  |
| Cozinha | `cozinha` | `cozinha123`  | `/cozinha` |

O cliente não tem login: abre `/mesa/<número>` pelo QR Code. Troque as senhas em **Equipe** antes de usar de verdade.

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

Testes:

```bash
pip install pytest
```

```bash
python -m pytest
```

Para rodar os mesmos testes num Postgres (o banco indicado é apagado), defina `TESTE_POSTGRES_URL`.
