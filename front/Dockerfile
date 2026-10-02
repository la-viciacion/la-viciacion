FROM nginx:alpine

# Nothing environment-specific is baked in: the nginx image renders the template below
# at start with these variables. The defaults match docker-compose.yml; override them
# with `environment:` (only these two are substituted, the rest of nginx's $vars are left alone).
ENV API_UPSTREAM=http://laviciacion-api:5000 \
    DNS_RESOLVER=127.0.0.11 \
    NGINX_ENVSUBST_FILTER='^(API_UPSTREAM|DNS_RESOLVER)$'

COPY . /usr/share/nginx/html
# the template is config, not content: it must not be served from the web root
RUN mkdir -p /etc/nginx/templates && mv /usr/share/nginx/html/nginx.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 3000
