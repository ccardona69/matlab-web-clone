%% Superficie 3D Peaks y Mapa de Contorno — Handle Graphics (hg.jar)
[X, Y, Z] = peaks(45);

figure(2);
clf;
subplot(1, 2, 1);
surf(X, Y, Z);
colormap('turbo');
colorbar();
title('Superficie 3D: peaks(45)');
xlabel('Eje X');
ylabel('Eje Y');
zlabel('Amplitud Z');

subplot(1, 2, 2);
contourf(X, Y, Z);
colormap('turbo');
title('Mapa de Contorno 2D: contourf(X, Y, Z)');
xlabel('Eje X');
ylabel('Eje Y');

z_max = max(Z);
z_min = min(Z);
fprintf('Rango de superficie peaks: [%.4f, %.4f]\n', z_min, z_max);
