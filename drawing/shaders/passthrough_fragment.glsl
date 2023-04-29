#version 130
#extension GL_ARB_explicit_attrib_location : require

uniform sampler2D tex;
in vec2 texcoord;

out vec4 out_colour;

void main()
{
    out_colour = texture(tex, texcoord);
}
