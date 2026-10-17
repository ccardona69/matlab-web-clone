% Regresion lineal - Ejemplo 1
x = [1 2 3 4 5]';
y = [2.1 3.9 6.2 8.1 9.9]';
p = polyfit(x, y, 1);
y_fit = polyval(p, x);
plot(x, y, 'ro', x, y_fit, 'b-');
title('Ajuste Lineal de Datos');
grid on;
