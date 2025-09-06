import { useState, useEffect, useRef } from 'react';

export default function AISpeakerBubble({ isSpeaking, className = "" }) {
  const [animationPhase, setAnimationPhase] = useState(0);
  const [particlePhase, setParticlePhase] = useState(0);
  const [glowIntensity, setGlowIntensity] = useState(0);
  const [rotationAngle, setRotationAngle] = useState(0);
  const [scaleFactor, setScaleFactor] = useState(1);
  const [opacityLevel, setOpacityLevel] = useState(0.8);
  const [colorShift, setColorShift] = useState(0);
  
  const animationRef = useRef();
  const particleRef = useRef();
  const glowRef = useRef();

  // Main animation loop
  useEffect(() => {
    const animate = () => {
      if (isSpeaking) {
        setAnimationPhase(prev => (prev + 0.015) % (2 * Math.PI));
        setParticlePhase(prev => (prev + 0.02) % (2 * Math.PI));
        setGlowIntensity(prev => Math.sin(animationPhase * 3) * 0.5 + 0.5);
        setRotationAngle(prev => prev + 0.5);
        setScaleFactor(1 + Math.sin(animationPhase * 2) * 0.08);
        setOpacityLevel(0.8 + Math.sin(animationPhase * 4) * 0.2);
        setColorShift(prev => (prev + 0.01) % (2 * Math.PI));
      } else {
        setAnimationPhase(0);
        setParticlePhase(0);
        setGlowIntensity(0.3);
        setRotationAngle(0);
        setScaleFactor(1);
        setOpacityLevel(0.8);
        setColorShift(0);
      }
      animationRef.current = requestAnimationFrame(animate);
    };
    
    animationRef.current = requestAnimationFrame(animate);
    return () => {
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, [isSpeaking, animationPhase]);

  // Particle system
  const generateParticles = (count, radius, sizeRange) => {
    return Array.from({ length: count }, (_, i) => {
      const angle = (i / count) * 2 * Math.PI + particlePhase;
      const distance = radius + Math.sin(particlePhase * 2 + i) * 10;
      const size = sizeRange[0] + Math.sin(particlePhase * 3 + i) * (sizeRange[1] - sizeRange[0]);
      const x = Math.cos(angle) * distance;
      const y = Math.sin(angle) * distance;
      const opacity = 0.3 + Math.sin(particlePhase * 4 + i) * 0.4;
      
      return { x, y, size, opacity, angle, distance };
    });
  };

  // Color generation functions
  const getGradientColors = () => {
    const shift = Math.sin(colorShift) * 20;
    return {
      primary: `rgb(${119 + shift}, ${91 + shift}, ${89 + shift})`,     // Secondary color base
      secondary: `rgb(${1 + shift}, ${38 + shift}, ${34 + shift})`,     // Dark green accent base  
      accent: `rgb(${50 + shift}, ${22 + shift}, ${31 + shift})`,       // Dark color base
      glow: `rgb(${1 + shift * 2}, ${38 + shift * 2}, ${34 + shift * 2})` // Dark green glow
    };
  };

  const colors = getGradientColors();

  return (
    <div className={`relative ${className}`} style={{ width: '120px', height: '120px' }}>
      {/* Ambient glow layers */}
      <div 
        className="absolute inset-0 rounded-full blur-3xl transition-all duration-1000"
        style={{
          background: `radial-gradient(circle, ${colors.glow}40 0%, ${colors.primary}20 50%, transparent 100%)`,
          transform: `scale(${1.5 + glowIntensity * 0.5})`,
          opacity: 0.6 + glowIntensity * 0.4,
        }}
      />
      
      {/* Outer ring system */}
      {isSpeaking && (
        <>
          <div 
            className="absolute inset-0 rounded-full border-2 border-white/20"
            style={{
              transform: `scale(${1.1 + Math.sin(animationPhase * 4) * 0.1}) rotate(${rotationAngle * 0.5}deg)`,
              animation: 'pulse 3s ease-in-out infinite',
            }}
          />
          <div 
            className="absolute inset-0 rounded-full border border-white/30"
            style={{
              transform: `scale(${1.2 + Math.sin(animationPhase * 3) * 0.15}) rotate(${-rotationAngle * 0.3}deg)`,
              animation: 'pulse 2.5s ease-in-out infinite',
              animationDelay: '0.5s',
            }}
          />
        </>
      )}

      {/* Main bubble container */}
      <div 
        className="relative w-full h-full rounded-full transition-all duration-700 ease-out"
        style={{
          transform: `scale(${scaleFactor}) rotate(${rotationAngle * 0.1}deg)`,
          opacity: opacityLevel,
        }}
      >
        {/* Primary glassmorphism layer */}
        <div 
          className="absolute inset-0 rounded-full"
          style={{
            background: `
              radial-gradient(circle at 30% 30%, 
                rgba(255, 255, 255, 0.9) 0%, 
                rgba(255, 255, 255, 0.6) 20%, 
                ${colors.primary}40 40%, 
                ${colors.secondary}30 60%, 
                ${colors.accent}20 80%, 
                transparent 100%
              )
            `,
            backdropFilter: 'blur(20px) saturate(180%)',
            border: '1px solid rgba(255, 255, 255, 0.4)',
            boxShadow: `
              0 8px 32px ${colors.primary}30,
              inset 0 1px 0 rgba(255, 255, 255, 0.6),
              inset 0 -1px 0 rgba(0, 0, 0, 0.1),
              ${isSpeaking ? `0 0 60px ${colors.glow}40` : `0 0 30px ${colors.primary}20`}
            `,
          }}
        />

        {/* Inner glow layer */}
        <div 
          className="absolute inset-2 rounded-full opacity-70"
          style={{
            background: `
              radial-gradient(circle at 40% 40%, 
                rgba(255, 255, 255, 0.95) 0%, 
                ${colors.primary}50 30%, 
                ${colors.secondary}30 60%, 
                transparent 100%
              )
            `,
            filter: 'blur(8px)',
            transform: isSpeaking 
              ? `rotate(${rotationAngle * 0.5}deg) scale(${1 + Math.sin(animationPhase * 3) * 0.1})`
              : 'rotate(0deg) scale(1)',
          }}
        />

        {/* Floating particles */}
        {isSpeaking && (
          <>
            {generateParticles(8, 45, [2, 4]).map((particle, i) => (
              <div
                key={`particle-${i}`}
                className="absolute rounded-full"
                style={{
                  left: `calc(50% + ${particle.x}px)`,
                  top: `calc(50% + ${particle.y}px)`,
                  width: `${particle.size}px`,
                  height: `${particle.size}px`,
                  transform: 'translate(-50%, -50%)',
                  background: `radial-gradient(circle, ${colors.glow}, ${colors.primary}80)`,
                  boxShadow: `0 0 ${particle.size * 2}px ${colors.glow}60`,
                  opacity: particle.opacity,
                  animation: 'float 4s ease-in-out infinite',
                  animationDelay: `${i * 0.2}s`,
                }}
              />
            ))}
            
            {generateParticles(12, 60, [1, 3]).map((particle, i) => (
              <div
                key={`small-particle-${i}`}
                className="absolute rounded-full"
                style={{
                  left: `calc(50% + ${particle.x}px)`,
                  top: `calc(50% + ${particle.y}px)`,
                  width: `${particle.size}px`,
                  height: `${particle.size}px`,
                  transform: 'translate(-50%, -50%)',
                  background: `radial-gradient(circle, ${colors.secondary}, ${colors.accent}80)`,
                  opacity: particle.opacity * 0.7,
                  animation: 'float 5s ease-in-out infinite',
                  animationDelay: `${i * 0.3}s`,
                }}
              />
            ))}
          </>
        )}

        {/* AI Icon */}
        <div className="absolute inset-0 flex items-center justify-center">
          <div 
            className="text-2xl transition-all duration-500"
            style={{
              transform: isSpeaking 
                ? `rotate(${Math.sin(animationPhase * 2) * 8}deg) scale(${1 + Math.sin(animationPhase * 4) * 0.1})`
                : 'rotate(0deg) scale(1)',
              filter: isSpeaking ? `drop-shadow(0 0 8px ${colors.glow})` : 'none',
              color: '#012622', // Primary text color
            }}
          >
            AI
          </div>
        </div>

        {/* Surface highlights */}
        <div 
          className="absolute inset-0 rounded-full opacity-40"
          style={{
            background: `
              radial-gradient(circle at 25% 25%, 
                rgba(255, 255, 255, 0.8) 0%, 
                rgba(255, 255, 255, 0.3) 30%, 
                transparent 70%
              )
            `,
            transform: isSpeaking 
              ? `rotate(${rotationAngle * 0.2}deg) scale(${1 + Math.sin(animationPhase * 2) * 0.05})`
              : 'rotate(0deg) scale(1)',
          }}
        />
      </div>

      {/* Speaking indicator */}
      {isSpeaking && (
        <div className="absolute -bottom-4 left-1/2 transform -translate-x-1/2">
          <div className="flex space-x-1">
            {[0, 1, 2].map((i) => (
              <div 
                key={i}
                className="w-2 h-2 rounded-full animate-pulse"
                style={{
                  background: colors.primary,
                  animationDelay: `${i * 150}ms`,
                  boxShadow: `0 0 8px ${colors.glow}`,
                }}
              />
            ))}
          </div>
        </div>
      )}

      {/* Energy field effect */}
      {isSpeaking && (
        <div 
          className="absolute inset-0 rounded-full"
          style={{
            background: `conic-gradient(from ${rotationAngle}deg, transparent, ${colors.primary}20, transparent)`,
            animation: 'spin 4s linear infinite',
            opacity: 0.3,
          }}
        />
      )}
    </div>
  );
}
