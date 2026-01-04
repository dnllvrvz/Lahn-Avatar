/** @type {import('tailwindcss').Config} */
module.exports = {
    darkMode: ["class"],
    content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
    "./src/components/**/*.{js,ts,jsx,tsx}", // if you have a components folder
  ],
  theme: {
  	extend: {
  		  fontFamily: {
  		    poetic: [
  		      'Gloock',
  		      'serif'
  		    ]
  		  },
        textShadow: {
          sm: '0 1px 2px var(--tw-shadow-color)',
          DEFAULT: '0 2px 4px var(--tw-shadow-color)',
          md: '0 4px 6px var(--tw-shadow-color)',
          lg: '0 8px 16px var(--tw-shadow-color)',
        },
        dropShadow: {
          'text': '0 1px 1px rgba(0, 0, 0, 0.8)',
          'text-md': '0 2px 2px rgba(0, 0, 0, 0.8)',
          'text-lg': '0 3px 3px rgba(0, 0, 0, 0.8)',
        },
  		animation: {
  			ripple: 'ripple 3s ease-in-out infinite',
  			breathe: 'breathe 4s ease-in-out infinite'
  		},
  		keyframes: {
  			ripple: {
  				'0%, 100%': {
  					transform: 'scale(1)',
  					opacity: '0.9'
  				},
  				'50%': {
  					transform: 'scale(1.02)',
  					opacity: '1'
  				}
  			},
  			breathe: {
  				'0%, 100%': {
  					transform: 'scale(1)'
  				},
  				'50%': {
  					transform: 'scale(1.05)'
  				}
  			}
  		},
  		borderRadius: {
  			lg: 'var(--radius)',
  			md: 'calc(var(--radius) - 2px)',
  			sm: 'calc(var(--radius) - 4px)'
  		},
  		colors: {
  			background: 'hsl(var(--background))',
  			foreground: 'hsl(var(--foreground))',
  			card: {
  				DEFAULT: 'hsl(var(--card))',
  				foreground: 'hsl(var(--card-foreground))'
  			},
  			popover: {
  				DEFAULT: 'hsl(var(--popover))',
  				foreground: 'hsl(var(--popover-foreground))'
  			},
  			primary: {
  				DEFAULT: 'hsl(var(--primary))',
  				foreground: 'hsl(var(--primary-foreground))'
  			},
  			secondary: {
  				DEFAULT: 'hsl(var(--secondary))',
  				foreground: 'hsl(var(--secondary-foreground))'
  			},
  			muted: {
  				DEFAULT: 'hsl(var(--muted))',
  				foreground: 'hsl(var(--muted-foreground))'
  			},
  			accent: {
  				DEFAULT: 'hsl(var(--accent))',
  				foreground: 'hsl(var(--accent-foreground))'
  			},
  			destructive: {
  				DEFAULT: 'hsl(var(--destructive))',
  				foreground: 'hsl(var(--destructive-foreground))'
  			},
  			border: 'hsl(var(--border))',
  			input: 'hsl(var(--input))',
  			ring: 'hsl(var(--ring))',
  			chart: {
  				'1': 'hsl(var(--chart-1))',
  				'2': 'hsl(var(--chart-2))',
  				'3': 'hsl(var(--chart-3))',
  				'4': 'hsl(var(--chart-4))',
  				'5': 'hsl(var(--chart-5))'
  			}
  		}
  	}
  },
  plugins: [
    require("tailwindcss-animate"),
    function ({ addUtilities, theme }) {
      const newUtilities = {
        '.text-shadow-sm': {
          textShadow: theme('textShadow.sm'),
        },
        '.text-shadow': {
          textShadow: theme('textShadow.DEFAULT'),
        },
        '.text-shadow-md': {
          textShadow: theme('textShadow.md'),
        },
        '.text-shadow-lg': {
          textShadow: theme('textShadow.lg'),
        },
      }
      addUtilities(newUtilities, ['responsive', 'hover'])
    }
  ],
};
