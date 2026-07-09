from ursina import Shader

# ==============================================================================
# ВЕРШИННЫЙ ШЕЙДЕР (VERTEX SHADER)
# Отвечает за проброс геометрии куба и текстурных координат во фрагментный шейдер
# ==============================================================================
vertex_shader = '''
#version 130

uniform mat4 p3d_ModelViewProjectionMatrix;
in vec4 p3d_Vertex;
in vec2 p3d_MultiTexCoord0;

out vec2 texcoord;

void main() {
    // Вычисляем финальную позицию вершины в 3D-пространстве экрана
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    // Передаем UV-координаты текстуры
    texcoord = p3d_MultiTexCoord0;
}
'''

# ==============================================================================
# ФРАГМЕНТНЫЙ ШЕЙДЕР (FRAGMENT SHADER)
# Управляет прозрачностью и неоновым свечением граней в зависимости от фокуса игрока
# ==============================================================================
fragment_shader = '''
#version 130

in vec2 texcoord;
out vec4 fragColor;

uniform vec4 base_color;      // Исходный цвет клетки (RGBA), переданный из Python
uniform float active_layer;   // Номер слоя, на который сейчас наведен курсор (0.0 - 7.0)
uniform float cell_layer;     // Номер слоя этой конкретной клетки (0.0 - 7.0)

void main() {
    // 1. Инициализируем базовый цвет клетки
    vec4 col = base_color;
    
    // 2. Вычисляем расстояние от этой клетки до слоя в фокусе игрока
    float layer_diff = abs(cell_layer - active_layer);
    
    // 3. Логика динамической прозрачности (Alpha Control)
    if (layer_diff < 0.1) {
        // Активный слой подсвечиваем сильнее (делаем его более контрастным)
        col.a = base_color.a * 2.5; 
    } else {
        // Неактивные слои плавно растворяем в пространстве, чтобы они не перекрывали обзор
        col.a = base_color.a * (1.0 / (layer_diff * 1.5));
    }
    
    // 4. Эффект голографического решетчатого куба (Glow Wireframe Effect)
    // edge_threshold задает толщину светящейся неоновой рамки на гранях кубика
    float edge_threshold = 0.04;
    if (texcoord.x < edge_threshold || texcoord.x > (1.0 - edge_threshold) ||
        texcoord.y < edge_threshold || texcoord.y > (1.0 - edge_threshold)) {
        
        // Окрашиваем ребра куба в ярко-бирюзовый неоновый цвет
        // Множитель альфа-канала (* 3.0) заставляет ребра светиться ярче, чем сама клетка
        fragColor = vec4(0.0, 0.8, 1.0, col.a * 3.0);
    } else {
        // Внутреннее пространство куба оставляем максимально прозрачным для видимости фигур
        fragColor = col;
    }
}
'''

# ==============================================================================
# ИНИЦИАЛИЗАЦИЯ ШЕЙДЕРА В ДВИЖКЕ URSINA
# ==============================================================================
cube_transparency_shader = Shader(
    vertex=vertex_shader,
    fragment=fragment_shader,
    name='CubeTransparencyShader'
)
