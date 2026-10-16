%% Dinámica No Lineal e Integración Runge-Kutta (ode45): Oscilador de Van der Pol
mu = 1.5;
vdp = @(t, y) [y(2); mu * (1 - y(1)^2) * y(2) - y(1)];

[t, Y] = ode45(vdp, [0, 25], [2.0, 0.0]);
x_pos = Y(:, 1);
x_vel = Y(:, 2);

figure(3);
clf;
subplot(1, 2, 1);
plot(t, x_pos, 'b-');
hold on;
plot(t, x_vel, 'y-');
title('Respuesta Temporal Oscilador Van der Pol (ode45)');
xlabel('Tiempo t (s)');
ylabel('Estado');
legend('Posición y_1(t)', 'Velocidad y_2(t)');

subplot(1, 2, 2);
plot(x_pos, x_vel, 'm-');
title('Retrato de Fase (Ciclo Límite)');
xlabel('Posición y_1');
ylabel('Velocidad y_2');

fprintf('Integración ode45 completada con %d pasos temporales.\n', length(t));
