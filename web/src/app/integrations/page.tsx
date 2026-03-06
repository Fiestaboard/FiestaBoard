"use client";

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, PluginInfo } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
  SheetFooter,
  SheetClose,
} from "@/components/ui/sheet";
import { SchemaForm } from "@/components/plugin-settings";
import { FIESTABOARD_COLORS, AVAILABLE_COLORS, FiestaboardColorName } from "@/lib/board-colors";
import { toast } from "sonner";
import {
  Cloud,
  Calendar,
  Home,
  Wifi,
  Sparkles,
  Wind,
  TrainFront,
  Waves,
  Bike,
  Car,
  TrendingUp,
  Plane,
  Puzzle,
  Settings,
  AlertCircle,
  CheckCircle,
  XCircle,
  Sun,
  Moon,
  Thermometer,
  Droplets,
  Zap,
  Music,
  Film,
  Gamepad2,
  BookOpen,
  Coffee,
  ShoppingCart,
  DollarSign,
  Bitcoin,
  Globe,
  MapPin,
  Navigation,
  Clock,
  Bell,
  MessageSquare,
  Mail,
  Phone,
  Camera,
  Image,
  Video,
  Mic,
  Volume2,
  Heart,
  Star,
  Award,
  Trophy,
  Target,
  Activity,
  BarChart,
  PieChart,
  LineChart,
  Database,
  Server,
  Cpu,
  HardDrive,
  Smartphone,
  Laptop,
  Monitor,
  Tv,
  Radio,
  Headphones,
  Speaker,
  Battery,
  BatteryCharging,
  Power,
  Lightbulb,
  Fan,
  Thermometer as ThermometerIcon,
  Umbrella,
  CloudRain,
  CloudSnow,
  CloudSun,
  Sunrise,
  Sunset,
  Eye,
  EyeOff,
  Lock,
  Unlock,
  Key,
  Shield,
  ShieldCheck,
  ShieldAlert,
  UserCircle,
  Users,
  Building,
  Building2,
  Factory,
  Store,
  Warehouse,
  Package,
  Gift,
  Trash,
  Trash2,
  Recycle,
  Leaf,
  TreePine,
  Flower2,
  Bug,
  Fish,
  Bird,
  Dog,
  Cat,
  Footprints,
  Dumbbell,
  Pill,
  Stethoscope,
  Syringe,
  Ambulance,
  Flame,
  Snowflake,
  Anchor,
  Ship,
  Rocket,
  Satellite,
  Radio as RadioIcon,
  Rss,
  Wifi as WifiIcon,
  WifiOff,
  Bluetooth,
  NfcIcon,
  QrCode,
  Barcode,
  Fingerprint,
  ScanFace,
  Bot,
  Cog,
  Wrench,
  Hammer,
  PenTool,
  Brush,
  Palette,
  Scissors,
  Ruler,
  Calculator,
  Binary,
  Code,
  Terminal,
  FileCode,
  FolderOpen,
  Folder,
  File,
  FileText,
  FileImage,
  FileVideo,
  FileAudio,
  Download,
  Upload,
  RefreshCw,
  RotateCcw,
  Repeat,
  Shuffle,
  Play,
  Pause,
  SkipForward,
  SkipBack,
  FastForward,
  Rewind,
  Volume,
  VolumeX,
  Maximize,
  Minimize,
  Move,
  Copy,
  Clipboard,
  ClipboardCheck,
  Check,
  X,
  Plus,
  Minus,
  Divide,
  Equal,
  Hash,
  AtSign,
  Percent,
  ArrowUp,
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ChevronUp,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronsUp,
  ChevronsDown,
  CornerUpRight,
  ExternalLink,
  Link as LinkIcon,
  Link2,
  Unlink,
  Paperclip,
  Pin,
  MapPinned,
  Compass,
  Map,
  Route,
  Signpost,
  Flag,
  Bookmark,
  Tag,
  Tags,
  Search,
  Filter,
  SortAsc,
  SortDesc,
  List,
  Grid,
  LayoutGrid,
  LayoutList,
  Columns,
  Rows,
  Table,
  Kanban,
  Trello,
  Calendar as CalendarIcon,
  CalendarDays,
  CalendarClock,
  AlarmClock,
  Timer,
  Hourglass,
  Watch,
  History,
  Archive,
  Inbox,
  Send,
  Reply,
  Forward,
  CornerUpLeft,
  MessageCircle,
  MessagesSquare,
  AtSign as AtSignIcon,
  Megaphone,
  Newspaper,
  ScrollText,
  FileSpreadsheet,
  Presentation,
  GraduationCap,
  School,
  Library,
  Landmark,
  Church,
  Tent,
  Mountain,
  Trees,
  Flower,
  Sprout,
  Apple,
  Cherry,
  Grape,
  Banana,
  Carrot,
  Beef,
  Egg,
  Croissant,
  Pizza,
  Sandwich,
  Soup,
  IceCream,
  Cake,
  Cookie,
  CupSoda,
  Beer,
  Wine,
  Martini,
  GlassWater,
  Milk,
  CircleDot,
  Disc,
  CirclePlay,
  CirclePause,
  CircleStop,
  Square,
  Circle,
  Triangle,
  Pentagon,
  Hexagon,
  Octagon,
  Diamond,
  Spade,
  Club,
  Gem,
  Crown,
  Wand,
  Wand2,
  PartyPopper,
  Confetti,
  Cake as CakeIcon,
  Balloon,
  Ghost,
  Skull,
  Smile,
  Frown,
  Meh,
  Angry,
  Laugh,
} from "lucide-react";
import { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import Link from "next/link";
import CountUp from "@/components/ui/react-bits/count-up";
import ShinyText from "@/components/ui/react-bits/shiny-text";

/**
 * Comprehensive icon mapping from Lucide icon names to components.
 * Plugins can specify any of these icons in their manifest.json.
 */
const ICON_MAP: Record<string, LucideIcon> = {
  // Weather & Environment
  cloud: Cloud,
  sun: Sun,
  moon: Moon,
  thermometer: Thermometer,
  droplets: Droplets,
  wind: Wind,
  umbrella: Umbrella,
  cloud_rain: CloudRain,
  cloudrain: CloudRain,
  cloud_snow: CloudSnow,
  cloudsnow: CloudSnow,
  cloud_sun: CloudSun,
  cloudsun: CloudSun,
  sunrise: Sunrise,
  sunset: Sunset,
  snowflake: Snowflake,
  flame: Flame,
  waves: Waves,
  
  // Transportation
  car: Car,
  bike: Bike,
  train: TrainFront,
  train_front: TrainFront,
  trainfront: TrainFront,
  plane: Plane,
  ship: Ship,
  rocket: Rocket,
  anchor: Anchor,
  navigation: Navigation,
  map_pin: MapPin,
  mappin: MapPin,
  compass: Compass,
  map: Map,
  route: Route,
  signpost: Signpost,
  
  // Home & Smart Home
  home: Home,
  lightbulb: Lightbulb,
  fan: Fan,
  power: Power,
  battery: Battery,
  battery_charging: BatteryCharging,
  batterycharging: BatteryCharging,
  wifi: Wifi,
  wifi_off: WifiOff,
  wifioff: WifiOff,
  bluetooth: Bluetooth,
  lock: Lock,
  unlock: Unlock,
  key: Key,
  shield: Shield,
  shield_check: ShieldCheck,
  shieldcheck: ShieldCheck,
  
  // Time & Calendar
  calendar: Calendar,
  calendar_days: CalendarDays,
  calendardays: CalendarDays,
  calendar_clock: CalendarClock,
  calendarclock: CalendarClock,
  clock: Clock,
  alarm_clock: AlarmClock,
  alarmclock: AlarmClock,
  timer: Timer,
  hourglass: Hourglass,
  watch: Watch,
  history: History,
  
  // Finance
  trending_up: TrendingUp,
  trendingup: TrendingUp,
  dollar_sign: DollarSign,
  dollarsign: DollarSign,
  bitcoin: Bitcoin,
  bar_chart: BarChart,
  barchart: BarChart,
  pie_chart: PieChart,
  piechart: PieChart,
  line_chart: LineChart,
  linechart: LineChart,
  activity: Activity,
  
  // Entertainment
  sparkles: Sparkles,
  music: Music,
  film: Film,
  gamepad2: Gamepad2,
  tv: Tv,
  radio: Radio,
  headphones: Headphones,
  speaker: Speaker,
  volume2: Volume2,
  play: Play,
  pause: Pause,
  party_popper: PartyPopper,
  partypopper: PartyPopper,
  
  // Communication
  message_square: MessageSquare,
  messagesquare: MessageSquare,
  message_circle: MessageCircle,
  messagecircle: MessageCircle,
  mail: Mail,
  phone: Phone,
  bell: Bell,
  megaphone: Megaphone,
  send: Send,
  rss: Rss,
  
  // Technology
  smartphone: Smartphone,
  laptop: Laptop,
  monitor: Monitor,
  cpu: Cpu,
  hard_drive: HardDrive,
  harddrive: HardDrive,
  server: Server,
  database: Database,
  globe: Globe,
  code: Code,
  terminal: Terminal,
  bot: Bot,
  satellite: Satellite,
  qr_code: QrCode,
  qrcode: QrCode,
  
  // Health & Fitness
  heart: Heart,
  activity2: Activity,
  dumbbell: Dumbbell,
  pill: Pill,
  stethoscope: Stethoscope,
  ambulance: Ambulance,
  apple: Apple,
  
  // Nature
  leaf: Leaf,
  tree_pine: TreePine,
  treepine: TreePine,
  flower2: Flower2,
  flower: Flower,
  sprout: Sprout,
  mountain: Mountain,
  trees: Trees,
  bug: Bug,
  fish: Fish,
  bird: Bird,
  dog: Dog,
  cat: Cat,
  
  // Food & Drink
  coffee: Coffee,
  pizza: Pizza,
  cake: Cake,
  cookie: Cookie,
  ice_cream: IceCream,
  icecream: IceCream,
  beer: Beer,
  wine: Wine,
  glass_water: GlassWater,
  glasswater: GlassWater,
  cup_soda: CupSoda,
  cupsoda: CupSoda,
  
  // Places
  building: Building,
  building2: Building2,
  factory: Factory,
  store: Store,
  warehouse: Warehouse,
  school: School,
  library: Library,
  landmark: Landmark,
  church: Church,
  tent: Tent,
  
  // Shopping
  shopping_cart: ShoppingCart,
  shoppingcart: ShoppingCart,
  package: Package,
  gift: Gift,
  tag: Tag,
  tags: Tags,
  
  // Actions & UI
  settings: Settings,
  cog: Cog,
  wrench: Wrench,
  hammer: Hammer,
  search: Search,
  filter: Filter,
  refresh_cw: RefreshCw,
  refreshcw: RefreshCw,
  download: Download,
  upload: Upload,
  eye: Eye,
  eye_off: EyeOff,
  eyeoff: EyeOff,
  
  // Status
  check_circle: CheckCircle,
  checkcircle: CheckCircle,
  alert_circle: AlertCircle,
  alertcircle: AlertCircle,
  x_circle: XCircle,
  xcircle: XCircle,
  check: Check,
  x: X,
  
  // Miscellaneous
  star: Star,
  award: Award,
  trophy: Trophy,
  target: Target,
  flag: Flag,
  bookmark: Bookmark,
  pin: Pin,
  link: LinkIcon,
  external_link: ExternalLink,
  externallink: ExternalLink,
  user_circle: UserCircle,
  usercircle: UserCircle,
  users: Users,
  zap: Zap,
  gem: Gem,
  crown: Crown,
  wand: Wand,
  wand2: Wand2,
  ghost: Ghost,
  skull: Skull,
  smile: Smile,
  book_open: BookOpen,
  bookopen: BookOpen,
  newspaper: Newspaper,
  graduation_cap: GraduationCap,
  graduationcap: GraduationCap,
  camera: Camera,
  image: Image,
  video: Video,
  mic: Mic,
  
  // Default fallback
  puzzle: Puzzle,
};

/**
 * Get the Lucide icon component for a plugin based on its manifest icon field.
 * Falls back to Puzzle icon if not found.
 */
function getPluginIcon(iconName?: string): LucideIcon {
  if (!iconName) return Puzzle;
  
  // Normalize: lowercase and handle both snake_case and lowercase
  const normalized = iconName.toLowerCase().replace(/-/g, '_');
  
  return ICON_MAP[normalized] || Puzzle;
}

// Color display helpers - using board's official colors
const COLOR_DISPLAY: Record<FiestaboardColorName, { bg: string; text: string; hex: string }> = {
  red: { bg: "bg-board-red", text: "text-board-white", hex: FIESTABOARD_COLORS.red },
  orange: { bg: "bg-board-orange", text: "text-board-black", hex: FIESTABOARD_COLORS.orange },
  yellow: { bg: "bg-board-yellow", text: "text-board-black", hex: FIESTABOARD_COLORS.yellow },
  green: { bg: "bg-board-green", text: "text-board-black", hex: FIESTABOARD_COLORS.green },
  blue: { bg: "bg-board-blue", text: "text-board-white", hex: FIESTABOARD_COLORS.blue },
  violet: { bg: "bg-board-violet", text: "text-board-white", hex: FIESTABOARD_COLORS.violet },
  white: { bg: "bg-board-white border", text: "text-board-black", hex: FIESTABOARD_COLORS.white },
  black: { bg: "bg-board-black", text: "text-board-white", hex: FIESTABOARD_COLORS.black },
};

// Available conditions for color rules
const AVAILABLE_CONDITIONS = [
  { value: ">=", label: ">= (greater or equal)" },
  { value: "<=", label: "<= (less or equal)" },
  { value: ">", label: "> (greater than)" },
  { value: "<", label: "< (less than)" },
  { value: "==", label: "== (equals)" },
  { value: "!=", label: "!= (not equals)" },
];

// Color rule types
interface ColorRule {
  condition: string;
  value: string | number;
  color: string;
}

interface ColorRulesConfig {
  [fieldName: string]: ColorRule[];
}

// Color Rules Editor Component
function ColorRulesEditor({
  pluginId,
  colorRules,
  onChange,
  onCopyVar,
  copiedVar,
}: {
  pluginId: string;
  colorRules: ColorRulesConfig;
  onChange: (rules: ColorRulesConfig) => void;
  onCopyVar: (varName: string) => void;
  copiedVar: string | null;
}) {
  const [newFieldName, setNewFieldName] = useState("");
  const [showAddField, setShowAddField] = useState(false);

  const handleUpdateRule = (fieldName: string, ruleIndex: number, updates: Partial<ColorRule>) => {
    const newRules = { ...colorRules };
    newRules[fieldName] = [...newRules[fieldName]];
    newRules[fieldName][ruleIndex] = { ...newRules[fieldName][ruleIndex], ...updates };
    onChange(newRules);
  };

  const handleDeleteRule = (fieldName: string, ruleIndex: number) => {
    const newRules = { ...colorRules };
    newRules[fieldName] = newRules[fieldName].filter((_, i) => i !== ruleIndex);
    if (newRules[fieldName].length === 0) {
      delete newRules[fieldName];
    }
    onChange(newRules);
  };

  const handleAddRule = (fieldName: string) => {
    const newRules = { ...colorRules };
    if (!newRules[fieldName]) {
      newRules[fieldName] = [];
    }
    newRules[fieldName] = [...newRules[fieldName], { condition: ">=", value: 0, color: "green" }];
    onChange(newRules);
  };

  const handleMoveRule = (fieldName: string, ruleIndex: number, direction: "up" | "down") => {
    const newRules = { ...colorRules };
    const rules = [...newRules[fieldName]];
    const newIndex = direction === "up" ? ruleIndex - 1 : ruleIndex + 1;
    if (newIndex < 0 || newIndex >= rules.length) return;
    [rules[ruleIndex], rules[newIndex]] = [rules[newIndex], rules[ruleIndex]];
    newRules[fieldName] = rules;
    onChange(newRules);
  };

  const handleAddField = () => {
    if (!newFieldName.trim()) return;
    const newRules = { ...colorRules };
    newRules[newFieldName.trim()] = [{ condition: ">=", value: 0, color: "green" }];
    onChange(newRules);
    setNewFieldName("");
    setShowAddField(false);
  };

  const handleDeleteField = (fieldName: string) => {
    const newRules = { ...colorRules };
    delete newRules[fieldName];
    onChange(newRules);
  };

  const fieldNames = Object.keys(colorRules);

  return (
    <TooltipProvider>
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium text-muted-foreground">
          Dynamic Colors
          <span className="ml-2 text-xs font-normal">(first match wins)</span>
        </h4>
        <Button
          variant="outline"
          size="sm"
          className="h-7 text-xs"
          onClick={() => setShowAddField(!showAddField)}
        >
          <Plus className="h-3 w-3 mr-1" />
          Add Field
        </Button>
      </div>

      {/* Add new field input */}
      {showAddField && (
        <div className="flex gap-2 p-2 rounded-md border bg-muted/30">
          <input
            type="text"
            value={newFieldName}
            onChange={(e) => setNewFieldName(e.target.value)}
            placeholder="Field name (e.g., temperature)"
            className="flex-1 h-8 px-2 text-xs rounded border bg-background"
          />
          <Button size="sm" className="h-8 text-xs" onClick={handleAddField}>
            Add
          </Button>
          <Button size="sm" variant="ghost" className="h-8 text-xs" onClick={() => setShowAddField(false)}>
            Cancel
          </Button>
        </div>
      )}

      {fieldNames.length === 0 ? (
        <p className="text-xs text-muted-foreground py-2">
          No color rules configured. Add a field to create dynamic colors.
        </p>
      ) : (
        <div className="space-y-3">
          {fieldNames.map((fieldName) => {
            const rules = colorRules[fieldName];
            return (
              <div key={fieldName} className="rounded-md border overflow-hidden">
                {/* Field header */}
                <div className="bg-muted/50 px-3 py-2 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <code className="text-xs font-mono text-primary bg-primary/10 px-1.5 py-0.5 rounded">
                      {pluginId}.{fieldName}
                    </code>
                    <span className="text-xs text-muted-foreground">→ color based on value</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => onCopyVar(`${fieldName}_color`)}
                      className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 px-2 py-1 rounded hover:bg-muted"
                    >
                      {copiedVar === `${fieldName}_color` ? (
                        <Check className="h-3 w-3 text-success" />
                      ) : (
                        <Copy className="h-3 w-3" />
                      )}
                      <code className="font-mono text-[10px]">{fieldName}_color</code>
                    </button>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <button
                          onClick={() => handleDeleteField(fieldName)}
                          className="p-1 text-destructive hover:bg-destructive/10 rounded"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </TooltipTrigger>
                      <TooltipContent>
                        <p>Delete all rules for this field</p>
                      </TooltipContent>
                    </Tooltip>
                  </div>
                </div>

                {/* Rules */}
                <div className="divide-y">
                  {rules.map((rule, idx) => {
                    const colorStyle = COLOR_DISPLAY[rule.color as FiestaboardColorName] || { bg: "bg-muted", text: "text-muted-foreground", hex: "#6b7280" };
                    return (
                      <div key={idx} className="px-3 py-2 flex items-center gap-2 text-xs">
                        {/* Reorder buttons */}
                        <div className="flex flex-col gap-0.5">
                          <button
                            onClick={() => handleMoveRule(fieldName, idx, "up")}
                            disabled={idx === 0}
                            className="p-0.5 hover:bg-muted rounded disabled:opacity-50"
                          >
                            <ArrowUp className="h-3 w-3" />
                          </button>
                          <button
                            onClick={() => handleMoveRule(fieldName, idx, "down")}
                            disabled={idx === rules.length - 1}
                            className="p-0.5 hover:bg-muted rounded disabled:opacity-50"
                          >
                            <ArrowDown className="h-3 w-3" />
                          </button>
                        </div>

                        {/* Color picker */}
                        <select
                          value={rule.color}
                          onChange={(e) => handleUpdateRule(fieldName, idx, { color: e.target.value })}
                          className="h-7 px-2 rounded border text-xs font-medium"
                          style={{ backgroundColor: colorStyle.hex, color: colorStyle.text === "text-board-black" ? "#000" : "#fff" }}
                        >
                          {AVAILABLE_COLORS.map((color) => (
                            <option key={color} value={color} className="bg-background text-foreground">
                              {color}
                            </option>
                          ))}
                        </select>

                        <span className="text-muted-foreground shrink-0">when</span>

                        {/* Condition picker */}
                        <select
                          value={rule.condition}
                          onChange={(e) => handleUpdateRule(fieldName, idx, { condition: e.target.value })}
                          className="h-7 px-2 rounded border bg-background text-xs font-mono"
                        >
                          {AVAILABLE_CONDITIONS.map((cond) => (
                            <option key={cond.value} value={cond.value}>
                              {cond.value}
                            </option>
                          ))}
                        </select>

                        {/* Value input */}
                        <input
                          type="text"
                          value={rule.value}
                          onChange={(e) => {
                            const val = e.target.value;
                            // Try to parse as number, otherwise keep as string
                            const numVal = parseFloat(val);
                            handleUpdateRule(fieldName, idx, { 
                              value: isNaN(numVal) ? val : numVal 
                            });
                          }}
                          className="w-20 h-7 px-2 rounded border bg-background text-xs font-mono"
                          placeholder="value"
                        />

                        {/* Delete button */}
                        <button
                          onClick={() => handleDeleteRule(fieldName, idx)}
                          className="p-1 text-destructive hover:bg-destructive/10 rounded ml-auto"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </div>
                    );
                  })}
                </div>

                {/* Add rule button */}
                <div className="px-3 py-2 border-t bg-muted/20">
                  <button
                    onClick={() => handleAddRule(fieldName)}
                    className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
                  >
                    <Plus className="h-3 w-3" />
                    Add rule
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <p className="text-xs text-muted-foreground">
        Rules are evaluated in order (first match wins). Use <code className="bg-muted px-1 rounded">{`{{${pluginId}.field_color}}`}</code> for just the color tile.
      </p>
    </div>
    </TooltipProvider>
  );
}

// Category labels
const CATEGORY_LABELS: Record<string, string> = {
  art: "Display Art",
  data: "Data & Information",
  entertainment: "Entertainment",
  finance: "Finance",
  home: "Smart Home",
  transit: "Transportation",
  utility: "Utilities",
  weather: "Weather & Environment",
};

interface PluginCardProps {
  plugin: PluginInfo;
  onToggle: (pluginId: string, enabled: boolean) => void;
  isToggling: boolean;
  onConfigUpdate: () => void;
  index?: number;
}

function PluginCard({ plugin, onToggle, isToggling, onConfigUpdate, index = 0 }: PluginCardProps) {
  const [isConfigOpen, setIsConfigOpen] = useState(false);
  const [configValues, setConfigValues] = useState<Record<string, unknown>>({});
  const [isSaving, setIsSaving] = useState(false);
  const [copiedVar, setCopiedVar] = useState<string | null>(null);

  // Fetch plugin details when opening config
  const { data: pluginDetails, isLoading: isLoadingDetails } = useQuery({
    queryKey: ["plugin", plugin.id],
    queryFn: () => api.getPlugin(plugin.id),
    enabled: isConfigOpen,
  });

  // Initialize config values when plugin details load
  useEffect(() => {
    if (pluginDetails?.config) {
      setConfigValues(pluginDetails.config);
    }
  }, [pluginDetails]);

  const handleSaveConfig = async () => {
    setIsSaving(true);
    try {
      await api.updatePluginConfig(plugin.id, configValues);
      toast.success(`${plugin.name} configuration saved`);
      onConfigUpdate();
      setIsConfigOpen(false);
    } catch (error) {
      toast.error(`Failed to save configuration: ${error instanceof Error ? error.message : "Unknown error"}`);
    } finally {
      setIsSaving(false);
    }
  };

  // Copy template variable
  const handleCopyVar = (varName: string) => {
    const templateVar = `{{${plugin.id}.${varName}}}`;
    navigator.clipboard.writeText(templateVar);
    setCopiedVar(varName);
    setTimeout(() => setCopiedVar(null), 2000);
    toast.success(`Copied ${templateVar}`);
  };

  // Parse variables from plugin details
  const getVariablesList = () => {
    if (!pluginDetails?.variables) return [];
    const variables = pluginDetails.variables as {
      simple?: string[];
      arrays?: Record<string, { label_field: string; item_fields: string[] }>;
    };
    const list: Array<{ name: string; description: string; maxChars: number }> = [];
    
    // Add simple variables
    if (variables.simple) {
      variables.simple.forEach(name => {
        list.push({
          name,
          description: name.replace(/_/g, ' '),
          maxChars: pluginDetails.max_lengths?.[name] || 22,
        });
      });
    }
    
    // Add array variables
    if (variables.arrays) {
      Object.entries(variables.arrays).forEach(([arrayName, config]) => {
        list.push({
          name: `${arrayName}.{index}.${config.label_field}`,
          description: `${arrayName} label`,
          maxChars: pluginDetails.max_lengths?.[`${arrayName}.${config.label_field}`] || 22,
        });
        // Skip label_field in item_fields to avoid duplicate keys
        config.item_fields
          .filter(field => field !== config.label_field)
          .forEach(field => {
            list.push({
              name: `${arrayName}.{index}.${field}`,
              description: `${arrayName} ${field.replace(/_/g, ' ')}`,
              maxChars: pluginDetails.max_lengths?.[`${arrayName}.${field}`] || 22,
            });
          });
      });
    }
    
    return list;
  };

  // Use icon from plugin manifest, falling back to Puzzle
  const Icon = getPluginIcon(plugin.icon);
  
  return (
    <div
      className="rounded-xl animate-card-fade-in"
      style={{ animationDelay: `${index * 60}ms` }}
    >
    <Card
      className={cn(
        "card-interactive",
        plugin.enabled ? "border-l-2 border-l-brand/50" : "opacity-75"
      )}
    >
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className={cn(
              "p-2 rounded-lg",
              plugin.enabled 
                ? "bg-primary/10 text-primary" 
                : "bg-muted text-muted-foreground"
            )}>
              <Icon className="h-5 w-5" />
            </div>
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                {plugin.name}
                <Badge variant="outline" className="text-xs font-normal">
                  v{plugin.version}
                </Badge>
              </CardTitle>
              <CardDescription className="text-xs mt-0.5">
                by {plugin.author}
              </CardDescription>
            </div>
          </div>
          <Switch
            checked={plugin.enabled}
            onCheckedChange={(checked) => onToggle(plugin.id, checked)}
            disabled={isToggling}
            aria-label={`Toggle ${plugin.name}`}
          />
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <p className="text-sm text-muted-foreground mb-3 line-clamp-2">
          {plugin.description}
        </p>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {plugin.enabled ? (
              plugin.configured ? (
                <Badge variant="default" className="text-xs gap-1">
                  <CheckCircle className="h-3 w-3" />
                  <ShinyText text="Configured" speed={4} className="text-xs" />
                </Badge>
              ) : (
                <Badge variant="secondary" className="text-xs gap-1">
                  <AlertCircle className="h-3 w-3" />
                  Setup Required
                </Badge>
              )
            ) : (
              <Badge variant="outline" className="text-xs gap-1">
                <XCircle className="h-3 w-3" />
                Disabled
              </Badge>
            )}
          </div>
          {plugin.enabled && (
            <Sheet open={isConfigOpen} onOpenChange={setIsConfigOpen}>
              <SheetTrigger asChild>
                <Button variant="ghost" size="sm" className="h-7 text-xs">
                  <Settings className="h-3 w-3 mr-1" />
                  Configure
                </Button>
              </SheetTrigger>
              <SheetContent className="w-full sm:max-w-xl overflow-y-auto">
                <SheetHeader>
                  <SheetTitle className="flex items-center gap-2">
                    <Icon className="h-5 w-5" />
                    {plugin.name}
                  </SheetTitle>
                  <SheetDescription>
                    Configure settings for this integration
                  </SheetDescription>
                </SheetHeader>
                <div className="py-6 space-y-6">
                  {isLoadingDetails ? (
                    <div className="space-y-4">
                      <Skeleton className="h-10 w-full" />
                      <Skeleton className="h-10 w-full" />
                      <Skeleton className="h-10 w-full" />
                    </div>
                  ) : (
                    <>
                      {/* Settings Section */}
                      {pluginDetails?.settings_schema && Object.keys(pluginDetails.settings_schema.properties || {}).length > 0 && (
                        <div className="space-y-4">
                          <h4 className="text-sm font-medium text-muted-foreground">Settings</h4>
                          <SchemaForm
                            schema={pluginDetails.settings_schema}
                            values={configValues}
                            onChange={setConfigValues}
                            disabled={isSaving}
                          />
                        </div>
                      )}

                      {/* Template Variables Section */}
                      {getVariablesList().length > 0 && (
                        <div className="space-y-3">
                          <h4 className="text-sm font-medium text-muted-foreground">
                            Template Variables
                            <span className="ml-2 text-xs font-normal">(click to copy)</span>
                          </h4>
                          <div className="rounded-md border overflow-hidden">
                            <table className="w-full text-xs">
                              <thead className="bg-muted/50">
                                <tr>
                                  <th className="text-left px-3 py-2 font-medium">Variable</th>
                                  <th className="text-left px-3 py-2 font-medium">Description</th>
                                  <th className="text-center px-3 py-2 font-medium">Max</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y">
                                {getVariablesList().map((variable) => (
                                  <tr 
                                    key={variable.name} 
                                    className="hover:bg-muted/30 cursor-pointer transition-colors"
                                    onClick={() => handleCopyVar(variable.name)}
                                  >
                                    <td className="px-3 py-2">
                                      <div className="flex items-center gap-1.5">
                                        <code className="text-primary font-mono bg-primary/10 px-1.5 py-0.5 rounded text-[11px]">
                                          {plugin.id}.{variable.name}
                                        </code>
                                        {copiedVar === variable.name ? (
                                          <Check className="h-3 w-3 text-success" />
                                        ) : (
                                          <Copy className="h-3 w-3 text-muted-foreground" />
                                        )}
                                      </div>
                                    </td>
                                    <td className="px-3 py-2 text-muted-foreground capitalize">
                                      {variable.description}
                                    </td>
                                    <td className="px-3 py-2 text-center">
                                      <Badge variant="outline" className="text-[10px]">
                                        {variable.maxChars}
                                      </Badge>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                          <p className="text-xs text-muted-foreground">
                            Use in templates as <code className="bg-muted px-1 rounded">{`{{${plugin.id}.variable}}`}</code>
                          </p>
                        </div>
                      )}

                      {/* Environment Variables Section */}
                      {pluginDetails?.env_vars && pluginDetails.env_vars.length > 0 && (
                        <div className="space-y-3">
                          <h4 className="text-sm font-medium text-muted-foreground">
                            Environment Variables
                          </h4>
                          <div className="rounded-md border overflow-hidden">
                            <table className="w-full text-xs">
                              <thead className="bg-muted/50">
                                <tr>
                                  <th className="text-left px-3 py-2 font-medium">Variable</th>
                                  <th className="text-left px-3 py-2 font-medium">Description</th>
                                  <th className="text-center px-3 py-2 font-medium">Required</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y">
                                {pluginDetails.env_vars.map((envVar) => (
                                  <tr key={envVar.name} className="hover:bg-muted/30">
                                    <td className="px-3 py-2">
                                      <code className="font-mono bg-muted px-1.5 py-0.5 rounded text-[11px]">
                                        {envVar.name}
                                      </code>
                                    </td>
                                    <td className="px-3 py-2 text-muted-foreground">
                                      {envVar.description}
                                    </td>
                                    <td className="px-3 py-2 text-center">
                                      {envVar.required ? (
                                        <Badge variant="destructive" className="text-[10px]">Required</Badge>
                                      ) : (
                                        <Badge variant="outline" className="text-[10px]">Optional</Badge>
                                      )}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}

                      {/* Color Rules Section */}
                      <ColorRulesEditor
                        pluginId={plugin.id}
                        colorRules={(configValues.color_rules as ColorRulesConfig) || {}}
                        onChange={(newRules) => {
                          setConfigValues((prev) => ({ ...prev, color_rules: newRules }));
                        }}
                        onCopyVar={handleCopyVar}
                        copiedVar={copiedVar}
                      />

                      {/* No config message */}
                      {(!pluginDetails?.settings_schema || Object.keys(pluginDetails.settings_schema.properties || {}).length === 0) && 
                       getVariablesList().length === 0 && (
                        <p className="text-sm text-muted-foreground">
                          No configuration options available for this plugin.
                        </p>
                      )}
                    </>
                  )}
                </div>
                <SheetFooter>
                  <SheetClose asChild>
                    <Button variant="outline" disabled={isSaving}>
                      Cancel
                    </Button>
                  </SheetClose>
                  <Button onClick={handleSaveConfig} disabled={isSaving || isLoadingDetails}>
                    {isSaving ? "Saving..." : "Save Changes"}
                  </Button>
                </SheetFooter>
              </SheetContent>
            </Sheet>
          )}
        </div>
      </CardContent>
    </Card>
    </div>
  );
}

function PluginCardSkeleton() {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <Skeleton className="h-9 w-9 rounded-lg" />
            <div>
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-3 w-16 mt-1" />
            </div>
          </div>
          <Skeleton className="h-5 w-9 rounded-full" />
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4 mt-1" />
        <div className="flex items-center justify-between mt-3">
          <Skeleton className="h-5 w-20" />
          <Skeleton className="h-7 w-20" />
        </div>
      </CardContent>
    </Card>
  );
}

export default function IntegrationsPage() {
  const queryClient = useQueryClient();

  // Fetch plugins list
  const { data, isLoading, error } = useQuery({
    queryKey: ["plugins"],
    queryFn: api.listPlugins,
    // No refetchInterval needed - already using optimistic updates
  });

  // Toggle plugin mutation
  const toggleMutation = useMutation({
    mutationFn: async ({ pluginId, enabled }: { pluginId: string; enabled: boolean }) => {
      if (enabled) {
        return api.enablePlugin(pluginId);
      } else {
        return api.disablePlugin(pluginId);
      }
    },
    onMutate: async ({ pluginId, enabled }) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: ["plugins"] });

      // Snapshot previous value
      const previousPlugins = queryClient.getQueryData(["plugins"]);

      // Optimistically update
      queryClient.setQueryData(["plugins"], (old: typeof data) => {
        if (!old) return old;
        return {
          ...old,
          plugins: old.plugins.map((p: PluginInfo) =>
            p.id === pluginId ? { ...p, enabled } : p
          ),
          enabled_count: enabled
            ? old.enabled_count + 1
            : old.enabled_count - 1,
        };
      });

      return { previousPlugins };
    },
    onError: (err, { pluginId }, context) => {
      // Roll back on error
      queryClient.setQueryData(["plugins"], context?.previousPlugins);
      toast.error(`Failed to toggle ${pluginId}: ${err instanceof Error ? err.message : 'Unknown error'}`);
    },
    onSuccess: (_, { pluginId, enabled }) => {
      toast.success(`${pluginId} ${enabled ? 'enabled' : 'disabled'}`);
    },
    onSettled: () => {
      // Refetch to ensure consistency
      queryClient.invalidateQueries({ queryKey: ["plugins"], refetchType: 'active' });
      // Invalidate template variables since plugin availability changed
      queryClient.invalidateQueries({ queryKey: ["template-variables"], refetchType: 'active' });
      // Invalidate plugin display data
      queryClient.invalidateQueries({ queryKey: ["plugin-displays-batch"], refetchType: 'active' });
      // Invalidate page previews since they may use plugin variables
      queryClient.invalidateQueries({ queryKey: ["pagePreview"], refetchType: 'active' });
    },
  });

  const handleToggle = (pluginId: string, enabled: boolean) => {
    toggleMutation.mutate({ pluginId, enabled });
  };

  // Group plugins by category
  const groupedPlugins = data?.plugins.reduce((acc, plugin) => {
    const category = plugin.category || "utility";
    if (!acc[category]) acc[category] = [];
    acc[category].push(plugin);
    return acc;
  }, {} as Record<string, PluginInfo[]>);

  return (
    <div className="min-h-screen bg-background overflow-x-hidden">
      <div className="container mx-auto px-3 sm:px-4 md:px-6 py-4 sm:py-6 md:py-8 max-w-full">
        {/* Header - Always visible */}
        <div className="mb-6 animate-card-fade-in" style={{ animationDelay: "0ms" }}>
          <h1 className="page-title flex items-center gap-3">
            <Puzzle className="h-7 w-7 text-brand-emphasis" />
            Integrations
          </h1>
          <p className="page-description">
            Enable and configure data source plugins for your FiestaBoard
          </p>
        </div>

        {/* Stats Bar - Progressive loading */}
        <div className="flex gap-4 mb-6 animate-card-fade-in" style={{ animationDelay: "100ms" }}>
          {isLoading ? (
            <>
              <div className="flex items-center gap-2 text-sm">
                <span className="text-muted-foreground">Total:</span>
                <Skeleton className="h-5 w-8" />
              </div>
              <div className="flex items-center gap-2 text-sm">
                <span className="text-muted-foreground">Enabled:</span>
                <Skeleton className="h-5 w-8" />
              </div>
            </>
          ) : data ? (
            <>
              <div className="flex items-center gap-2 text-sm">
                <span className="text-muted-foreground">Total:</span>
                <Badge variant="outline"><CountUp to={data.total} duration={1} /></Badge>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <span className="text-muted-foreground">Enabled:</span>
                <Badge variant="default"><CountUp to={data.enabled_count} duration={1} /></Badge>
              </div>
            </>
          ) : null}
        </div>

        {/* Content - Progressive loading */}
        {isLoading ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {[...Array(6)].map((_, i) => (
              <PluginCardSkeleton key={i} />
            ))}
          </div>
        ) : error ? (
          <Card className="border-destructive">
            <CardContent className="flex items-center gap-3 py-6">
              <AlertCircle className="h-5 w-5 text-destructive" />
              <p className="text-sm text-destructive">
                Failed to load plugins: {error instanceof Error ? error.message : 'Unknown error'}
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-8 animate-card-fade-in" style={{ animationDelay: "150ms" }}>
            {(() => {
              let globalIndex = 0;
              return Object.entries(groupedPlugins || {})
                .sort(([a], [b]) => (CATEGORY_LABELS[a] || a).localeCompare(CATEGORY_LABELS[b] || b))
                .map(([category, plugins]) => (
                <section key={category}>
                  <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                    {CATEGORY_LABELS[category] || category}
                    <Badge variant="secondary" className="text-xs font-normal">
                      {plugins.length}
                    </Badge>
                  </h2>
                  <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                    {plugins.map((plugin) => {
                      const cardIndex = globalIndex++;
                      return (
                        <PluginCard
                          key={plugin.id}
                          plugin={plugin}
                          onToggle={handleToggle}
                          isToggling={toggleMutation.isPending}
                          onConfigUpdate={() => queryClient.invalidateQueries({ queryKey: ["plugins"] })}
                          index={cardIndex}
                        />
                      );
                    })}
                  </div>
                </section>
              ));
            })()}
          </div>
        )}
      </div>
    </div>
  );
}

