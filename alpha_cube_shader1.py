from ursina import Shader

# ==============================================================================
# ВЕРШИННЫЙ ШЕЙДЕР (VERTEX SHADER)
# ==============================================================================
vertex_shader = '''
#version 130

uniform mat4 p3d_ModelViewProjectionMatrix;
in vec4 p3d_Vertex;
in vec2 p3d_MultiTexCoord0;

out vec2 texcoord;

void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    texcoord = p3d_MultiTexCoord0;
}
'''

# ==============================================================================
# ФРАГМЕНТНЫЙ ШЕЙДЕР (FRAGMENT SHADER)
# ==============================================================================
fragment_shader = '''
#version 130

in vec2 texcoord;
out vec4 fragColor;

uniform vec4 base_color;
uniform float active_layer;
uniform float cell_layer;

void main() {
    vec4 col = base_color;
    float layer_diff = abs(cell_layer - active_layer);
    
    if (layer_diff < 0.1) {
        col.a = base_color.a * 2.5;
    } else {
        col.a = base_color.a * (1.0 / (layer_diff * 1.5));
    }
    
    float edge_threshold = 0.04;
    if (texcoord.x < edge_threshold || texcoord.x > (1.0 - edge_threshold) ||
        texcoord.y < edge_threshold || texcoord.y > (1.0 - edge_threshold)) {
        fragColor = vec4(0.0, 0.8, 1.0, col.a * 3.0);
    } else {
        fragColor = col;
    }
}
'''

# ==============================================================================
# ИНИЦИАЛИЗАЦИЯ ШЕЙДЕРА
# ==============================================================================
cube_transparency_shader = Shader(
    vertex=vertex_shader,
    fragment=fragment_shader,
    name='CubeTransparencyShader'
)
