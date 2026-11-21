# GrillKit frontend container.
#
# Serves the static Vanilla SPA and reverse-proxies API/WebSocket/media
# traffic to the backend service. The frontend is the public entry point.
FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/nginx.conf
COPY public /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
